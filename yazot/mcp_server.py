import asyncio
import json
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .chunker import ResponseChunker, TextChunker
from .client_router import ZoteroClientRouter
from .config import Settings
from .crossref_client import CrossrefClient
from .exceptions import ConfigurationError, ZoteroError, ZoteroNotFoundError
from .fulltext_resolver import FulltextResolver
from .models import (
    CollectionCreate,
    ExternalFulltextResponse,
    FulltextResponse,
    ItemUpdate,
    Note,
    SearchCollectionResponse,
    VerificationResult,
    ZoteroCollectionBase,
    ZoteroItem,
    ZoteroSearchParams,
    ZoteroTag,
)
from .note_manager import NoteManager
from .verifier import NoteVerifier

logger = logging.getLogger(__name__)


def _deps(ctx: Context) -> dict[str, Any]:
    """Get lifespan dependencies from request context."""
    return ctx.lifespan_context


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Initialize all dependencies at server start, clean up on shutdown."""
    settings = Settings()
    router = ZoteroClientRouter(settings)
    crossref = CrossrefClient()
    chunker = ResponseChunker(max_tokens=settings.max_chunk_size)
    text_chunker = TextChunker(max_tokens=settings.max_chunk_size)
    note_manager = NoteManager(router)
    verifier = NoteVerifier(note_manager, router)
    resolver = FulltextResolver(settings)

    try:
        yield {
            "settings": settings,
            "router": router,
            "crossref": crossref,
            "chunker": chunker,
            "text_chunker": text_chunker,
            "note_manager": note_manager,
            "verifier": verifier,
            "resolver": resolver,
        }
    finally:
        await crossref.aclose()
        await resolver.aclose()


# Create FastMCP server with error masking for security
# Custom exceptions (ToolError subclasses) will still show details to clients
mcp: FastMCP = FastMCP(
    "zotero-mcp",
    lifespan=app_lifespan,
    mask_error_details=True,
    instructions="""
## Chunking
All search and fulltext tools may return chunked responses.
If `has_more=True`, call `get_next_chunk` (search results) or `get_next_fulltext_chunk` (text) with the provided `chunk_id`. Repeat until `has_more=False`.

## Typical Workflows

**Get list of items from Collection with given name**
1. List all collections with resource://collections
2. Find collection with given name and get its key
3. If several collections with same name were found ask user which collection to use
3. Use tool get_collection_items with this key

**Search and read articles:**
1. `search_articles(query="machine learning")` or `get_collection_items(collection_key="ABC123")`
2. If `has_more=True`, call `get_next_chunk(chunk_id)` repeatedly
3. For specific item, call `get_item_fulltext(item_key)`
   **Note:** `search_articles` does NOT indicate fulltext availability.
   If `get_item_fulltext` returns "No fulltext available", try `fetch_external_fulltext(item_key)` —
   it downloads PDFs from open access sources (Unpaywall, CORE) and attaches them to the item.
   Do NOT try `get_item_fulltext` on many items hoping to find one with text.
4. If fulltext `has_more=True`, call `get_next_fulltext_chunk(chunk_id)` repeatedly

**Fetch fulltext from external sources:**
1. `fetch_external_fulltext(item_key="ABC123")` — uses DOI from item, attaches PDF
2. Or `fetch_external_fulltext(doi="10.1234/example")` — standalone search by DOI
3. Or `fetch_external_fulltext(title="Article title")` — search by title
4. If `has_more=True`, call `get_next_fulltext_chunk(chunk_id)` repeatedly

**Add/move articles to collection:**
1. Search for articles using `search_articles` or `get_collection_items`
2. Use `add_items_to_collection(collection_key, item_keys)` to add found items
3. Use `add_item_by_doi` ONLY for articles not yet in your library

**Import new article by DOI:**
1. `add_item_by_doi(doi="10.1234/example", collection_key="ABC123", tags=["important"])`
2. Metadata auto-fetched from Crossref

**Remove items:**
1. Find item using search or get_collection_items
2. `remove_item(item_key="ABC123", collection_key="COL456")` — smart removal
3. Or `remove_item(item_key="ABC123", from_library=True)` — force delete from library

**Manage item tags:**
1. Find item using search or get_collection_items
2. `update_item_tags(item_key="ABC123", tags=["important", "to-read"])` — add tags (default)
3. `update_item_tags(item_key="ABC123", tags=["to-read"], mode="remove")` — remove specific tags
4. `update_item_tags(item_key="ABC123", tags=["reviewed"], mode="replace")` — replace all tags

**Create and verify notes:**
1. Find item using search or get_collection_items tool
2. `create_note_for_item(item_key, title, content)` — use `> quote` for citations
3. `verify_note(note_key)` — checks quotes against fulltext, adds verified/unverified tag
4. Review with `get_item_notes(item_key)`

**Important:** Always handle chunked responses completely before proceeding to next operation.
""",
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
async def get_collection_items(
    collection_key: str,
    ctx: Context,
    include_subcollections: bool = False,
) -> SearchCollectionResponse:
    """
    Search and evaluate items in a specific collection.
    Returns items with abstracts and metadata for assessment.

    Args:
        collection_key: The collection key to retrieve items from
        include_subcollections: If True, recursively include items from all subcollections (default: False)

    Returns:
        SearchCollectionResponse with items from the collection

    Note:
        To get full text content for an item, use the separate 'get_item_fulltext' tool.

    IMPORTANT CHUNKING BEHAVIOR:
    - If response contains 'has_more=True', there are more results available
    - You MUST call 'get_next_chunk' tool with the provided 'chunk_id' to retrieve remaining data
    - Continue calling 'get_next_chunk' until 'has_more=False'
    - The 'current_chunk' and 'total_chunks' fields show progress (e.g., current_chunk=1, total_chunks=3)
    - The 'message' field provides specific instructions for retrieving next chunk
    """
    router: ZoteroClientRouter = _deps(ctx)["router"]
    chunker: ResponseChunker = _deps(ctx)["chunker"]

    collection = await router.get_collection(key=collection_key)
    if not collection:
        raise ZoteroNotFoundError("collection", collection_key)

    async def collect_items_recursive(coll: ZoteroCollectionBase) -> list[ZoteroItem]:
        if not include_subcollections:
            return await coll.get_items()

        items, subcollections = await asyncio.gather(coll.get_items(), coll.get_subcollections())

        if not subcollections:
            return items

        await ctx.info(f"Traversing {len(subcollections)} subcollections")

        results = await asyncio.gather(
            *(collect_items_recursive(sub) for sub in subcollections),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                if not isinstance(result, httpx.ConnectError | httpx.TimeoutException):
                    raise result
                logger.warning("Failed to fetch subcollection: %s", result)
                continue
            items.extend(result)

        return items

    # Collect items (with or without subcollections)
    filtered_items = await collect_items_recursive(collection)

    # Remove duplicates by key (items can appear in multiple collections)
    seen_keys = set()
    unique_items = []
    for item in filtered_items:
        if item.key not in seen_keys:
            seen_keys.add(item.key)
            unique_items.append(item)

    filtered_items = unique_items
    await ctx.debug("\n".join([str(i) for i in filtered_items]))

    return chunker.build_chunked_response(filtered_items, len(filtered_items)).to_slim_dict()  # type: ignore[return-value]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
async def get_next_chunk(chunk_id: str, ctx: Context) -> SearchCollectionResponse:
    """
    Get next chunk of search results.

    Use this tool when 'search_collection' returns 'has_more=True'.
    Pass the 'chunk_id' from the previous response to retrieve the next batch of items.
    Continue calling until 'has_more=False' to get all results.

    Raises:
        ZoteroNotFoundError: If chunk_id is invalid or expired
    """
    chunker: ResponseChunker = _deps(ctx)["chunker"]
    chunk_response = chunker.get_next_chunk(chunk_id)

    message = None
    if chunk_response.has_more:
        message = (
            f"⚠️ More results available ({chunk_response.chunk_info}). "
            f"Call: get_next_chunk(chunk_id='{chunk_response.chunk_id}')"
        )
    else:
        message = f"✓ All results retrieved ({chunk_response.chunk_info})."

    return SearchCollectionResponse(
        items=chunk_response.items,
        count=len(chunk_response.items),
        has_more=chunk_response.has_more,
        chunk_id=chunk_response.chunk_id,
        current_chunk=chunk_response.current_chunk,
        total_chunks=chunk_response.total_chunks,
        message=message,
    ).to_slim_dict()  # type: ignore[return-value]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
async def search_articles(
    ctx: Context,
    query: str | None = None,
    tags: list[str] | None = None,
    collection_key: str | None = None,
    item_type: str | None = None,
) -> SearchCollectionResponse:
    """
    Search for articles by name, tags, collections, or item type.

    Supports flexible searching across your Zotero library with multiple filter options.

    Note:
        To get full text content for an item, use the separate 'get_item_fulltext' tool.

    IMPORTANT CHUNKING BEHAVIOR:
    - If response contains 'has_more=True', there are more results available
    - You MUST call 'get_next_chunk' tool with the provided 'chunk_id' to retrieve remaining data
    - Continue calling 'get_next_chunk' until 'has_more=False'
    - The 'current_chunk' and 'total_chunks' fields show progress
    - The 'message' field provides specific instructions for retrieving next chunk

    Examples:
        # Search by title/creator
        search_articles(query="machine learning")

        # Filter by tags (AND logic)
        search_articles(tags=["important", "to-read"])

        # Search within collection
        search_articles(collection_key="ABC123XYZ")

        # Combine filters
        search_articles(query="neural networks", tags=["AI"], item_type="journalArticle")
    """
    search_params = ZoteroSearchParams(q=query, tag=tags, item_type=item_type)
    router: ZoteroClientRouter = _deps(ctx)["router"]
    chunker: ResponseChunker = _deps(ctx)["chunker"]

    # Execute search using router (implements protocol with fallback)
    if collection_key:
        # Server-side search within collection via Zotero API
        filtered_items = await router.search_collection_items(collection_key, search_params)
    else:
        # Search across entire library using search_items method
        filtered_items = await router.search_items(search_params)

    # Manual tag filtering if needed (pyzotero may not support all tag logic)
    if search_params.tag:
        tag_filter = (
            [search_params.tag] if isinstance(search_params.tag, str) else search_params.tag
        )
        filtered_items = [
            item
            for item in filtered_items
            if all(t in {tag.tag for tag in item.data.tags} for t in tag_filter)
        ]

    return chunker.build_chunked_response(filtered_items, len(filtered_items)).to_slim_dict()  # type: ignore[return-value]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def create_note_for_item(
    item_key: str,
    title: str,
    content: str | dict[str, Any],
    ctx: Context,
    tags: list[str] | None = None,
) -> Note:
    """
    Create a new note for a Zotero item/article.

    Args:
        item_key: The Zotero item key to attach the note to
        title: Title of the note
        content: Note content - can be plain text string or structured dict
        tags: Optional list of tags to apply to the note

    Returns:
        Note object with key, content, timestamps, and tags
    """
    note_manager: NoteManager = _deps(ctx)["note_manager"]

    # Format content if it's a dict
    if isinstance(content, dict):
        formatted_content = f"# {title}\n\n{json.dumps(content, indent=2)}"
    else:
        formatted_content = f"# {title}\n\n{content}"

    note = await note_manager.create_note(item_key=item_key, content=formatted_content, tags=tags)

    return note


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
async def get_item_notes(item_key: str, ctx: Context) -> list[Note]:
    """
    Get all notes for a specific Zotero item/article.

    Retrieves all notes attached to the specified item, including their content,
    timestamps, and tags.

    Args:
        item_key: The Zotero item key to retrieve notes from

    Returns:
        List of Note objects with key, content, timestamps, and tags

    Note:
        This endpoint uses the web API as local Zotero API does not yet support
        retrieving notes. Make sure web API credentials are configured.

    Example:
        # Get all notes for an article
        notes = get_item_notes("ABC123XYZ")
        for note in notes:
            print(f"{note.key}: {note.content[:100]}")
    """
    note_manager: NoteManager = _deps(ctx)["note_manager"]
    notes = await note_manager.get_notes_for_item(item_key=item_key)
    return notes


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def create_collection(
    name: str, ctx: Context, parent_collection_key: str | None = None
) -> dict[str, Any]:
    """
    Create a new collection in Zotero library.

    Collections are used to organize items in your library. You can create
    top-level collections or nested subcollections by specifying a parent.

    Args:
        name: Name of the new collection
        parent_collection_key: Optional parent collection key for creating subcollections

    Returns:
        Dictionary with collection details including key, name, and version

    Note:
        This operation requires web API access with write permissions.
        Make sure ZOTERO_API_KEY is configured with write access.

    Examples:
        # Create a top-level collection
        create_collection(name="Machine Learning Papers")

        # Create a subcollection
        parent = create_collection(name="AI Research")
        create_collection(name="Neural Networks", parent_collection_key=parent["key"])
    """
    router: ZoteroClientRouter = _deps(ctx)["router"]

    collection_data = CollectionCreate(name=name, parent_collection=parent_collection_key)

    created_collections = await router.create_collections([collection_data])

    if not created_collections:
        raise ZoteroError("Failed to create collection")

    created = created_collections[0]
    return {
        "key": created.key,
        "name": created.name,
        "version": created.version,
        "parent_collection": parent_collection_key,
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True))
async def add_item_by_doi(
    doi: str,
    ctx: Context,
    collection_key: str | None = None,
    tags: list[str] | None = None,
) -> ZoteroItem:
    """
    Add a new item to Zotero library by DOI (Digital Object Identifier).

    This tool automatically fetches bibliographic metadata from Crossref API
    using the provided DOI, converts it to Zotero format, and creates the item
    in your library. Optionally adds the item to a collection and applies tags.

    Args:
        doi: Digital Object Identifier (e.g., "10.1234/example" or "https://doi.org/10.1234/example")
        collection_key: Optional collection key to add the item to after creation
        tags: Optional list of tags to apply to the item

    Returns:
        ZoteroItem object with the created item details
    """
    router: ZoteroClientRouter = _deps(ctx)["router"]
    crossref: CrossrefClient = _deps(ctx)["crossref"]

    crossref_metadata = await crossref.get_metadata_by_doi(doi)
    item_create = crossref.crossref_to_zotero(crossref_metadata)

    if tags:
        item_create.tags = [ZoteroTag(tag=tag) for tag in tags]

    if collection_key:
        item_create.collections = [collection_key]

    created_items = await router.create_items([item_create])

    if not created_items:
        raise ZoteroError("Failed to create item from DOI")

    return created_items[0]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def add_items_to_collection(
    collection_key: str,
    item_keys: list[str],
    ctx: Context,
) -> str:
    """
    Add existing Zotero items to a collection.

    Use this tool to organize items that are already in your library into collections.
    This does NOT create duplicates — it adds references to existing items.

    For importing new articles not yet in your library, use add_item_by_doi instead.

    Args:
        collection_key: Target collection key (use resource://collections to find keys)
        item_keys: List of item keys to add to the collection

    Returns:
        Confirmation message with the number of items added
    """
    router: ZoteroClientRouter = _deps(ctx)["router"]

    items = [await router.get_item(key) for key in item_keys]
    await router.add_to_collection(collection_key, items)

    return f"Added {len(items)} item(s) to collection {collection_key}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
async def get_item_fulltext(item_key: str, ctx: Context) -> FulltextResponse:
    """
    Get full text content for a Zotero item (e.g., from PDF attachment).

    Returns the text content with automatic chunking if the text is too large
    to fit in a single response.

    This tool uses a two-tier approach for maximum reliability:
    1. First tries Zotero's pre-indexed fulltext API (fast)
    2. If unavailable, automatically downloads and parses PDF directly (fallback)

    Args:
        item_key: The Zotero item key to get fulltext for

    Returns:
        FulltextResponse with text content (potentially chunked)

    IMPORTANT CHUNKING BEHAVIOR:
    - If response contains 'has_more=True', there are more text chunks available
    - You MUST call 'get_next_fulltext_chunk' tool with the provided 'chunk_id'
    - Continue calling until 'has_more=False' to get the complete text
    - The 'current_chunk' and 'total_chunks' fields show progress
    - Text is intelligently split by paragraphs and sentences for readability
    """
    router: ZoteroClientRouter = _deps(ctx)["router"]
    text_chunker: TextChunker = _deps(ctx)["text_chunker"]

    fulltext = await router.get_fulltext(item_key)

    if not fulltext:
        await ctx.info("Indexed fulltext not available, extracting from PDF")
        fulltext = await router.get_pdf_text(item_key)

    if not fulltext:
        return FulltextResponse(
            item_key=item_key,
            content="",
            error="No fulltext available for this item",
        ).to_slim_dict()  # type: ignore[return-value]

    if not text_chunker.needs_chunking(fulltext):
        return FulltextResponse(
            item_key=item_key,
            content=fulltext,
        ).to_slim_dict()  # type: ignore[return-value]

    chunk_data = text_chunker.chunk_text(fulltext, item_key)

    message = None
    if chunk_data.has_more:
        message = (
            f"⚠️ Fulltext chunked ({chunk_data.chunk_info}). "
            f"To get remaining text, call: "
            f"get_next_fulltext_chunk(chunk_id='{chunk_data.chunk_id}')"
        )

    return FulltextResponse(
        item_key=chunk_data.item_key,
        content=chunk_data.content,
        has_more=chunk_data.has_more,
        chunk_id=chunk_data.chunk_id,
        current_chunk=chunk_data.current_chunk,
        total_chunks=chunk_data.total_chunks,
        message=message,
    ).to_slim_dict()  # type: ignore[return-value]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
async def get_next_fulltext_chunk(chunk_id: str, ctx: Context) -> FulltextResponse:
    """
    Get next chunk of fulltext content.

    Use this tool when 'get_item_fulltext' returns 'has_more=True'.
    Pass the 'chunk_id' from the previous response to retrieve the next part.
    Continue calling until 'has_more=False' to get all text.

    Args:
        chunk_id: The chunk ID from previous fulltext response

    Returns:
        FulltextResponse with next chunk of text

    Raises:
        ZoteroNotFoundError: If chunk_id is invalid or expired
    """
    text_chunker: TextChunker = _deps(ctx)["text_chunker"]
    chunk_data = text_chunker.get_next_text_chunk(chunk_id)

    message = None
    if chunk_data.has_more:
        message = (
            f"⚠️ More text available ({chunk_data.chunk_info}). "
            f"Call: get_next_fulltext_chunk(chunk_id='{chunk_data.chunk_id}')"
        )
    elif chunk_data.current_chunk and chunk_data.total_chunks:
        message = f"✓ All text retrieved ({chunk_data.chunk_info})."

    return FulltextResponse(
        item_key=chunk_data.item_key,
        content=chunk_data.content,
        has_more=chunk_data.has_more,
        chunk_id=chunk_data.chunk_id,
        current_chunk=chunk_data.current_chunk,
        total_chunks=chunk_data.total_chunks,
        message=message,
    ).to_slim_dict()  # type: ignore[return-value]


@mcp.tool(annotations=ToolAnnotations(idempotentHint=True))
async def verify_note(note_key: str, ctx: Context) -> VerificationResult:
    """
    Verify that quotes in a note actually exist in the parent article's fulltext.

    Extracts all blockquotes (lines starting with '>' in markdown) from the note,
    then checks each quote against the article's full text using normalized comparison.

    If all quotes are found, adds 'verified' tag to the note.
    If any quote is missing or fulltext is unavailable, adds 'unverified' tag.

    Args:
        note_key: The Zotero key of the note to verify

    Returns:
        VerificationResult with verification status, quote counts, and failed quotes

    Example workflow:
        1. Create a note with blockquotes:
           create_note_for_item(item_key, "Analysis", "The authors state:\\n> exact quote from article")
        2. Verify the quotes: verify_note(note_key)
    """
    verifier: NoteVerifier = _deps(ctx)["verifier"]
    await ctx.info("Verifying quotes against article fulltext")
    return await verifier.verify(note_key)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True))
async def fetch_external_fulltext(
    ctx: Context,
    item_key: str | None = None,
    doi: str | None = None,
    title: str | None = None,
) -> ExternalFulltextResponse:
    """
    Fetch full text of an article from external open-access sources.

    Searches external sources in cascade order:
    1. Unpaywall (by DOI) - legal open-access repository
    2. CORE (by DOI or title) - academic aggregator
    3. Libgen (by title) - only if explicitly enabled in config

    If item_key is provided, DOI/title are extracted from the Zotero item automatically,
    and the downloaded PDF is attached to the item.

    At least one of item_key, doi, or title must be provided.

    Args:
        item_key: Optional Zotero item key — extracts DOI/title and attaches PDF
        doi: DOI identifier (preferred for best results)
        title: Article title (used for CORE and libgen search)

    Returns:
        ExternalFulltextResponse with extracted text content (potentially chunked)

    IMPORTANT CHUNKING BEHAVIOR:
    - If response contains 'has_more=True', there are more text chunks
    - Call 'get_next_fulltext_chunk' with the provided 'chunk_id'
    - Continue calling until 'has_more=False'
    """
    resolver: FulltextResolver = _deps(ctx)["resolver"]
    router: ZoteroClientRouter = _deps(ctx)["router"]
    text_chunker: TextChunker = _deps(ctx)["text_chunker"]

    if not resolver.is_configured:
        raise ConfigurationError(
            "External fulltext retrieval is not configured. "
            "Set UNPAYWALL_EMAIL and/or CORE_API_KEY in .env"
        )

    # Extract DOI/title from Zotero item if item_key provided
    effective_doi = doi
    effective_title = title
    if item_key:
        item = await router.get_item(item_key)
        if not effective_doi:
            effective_doi = item.data.doi or None
        if not effective_title:
            effective_title = item.data.title or None

    if not effective_doi and not effective_title:
        raise ZoteroError("At least one of doi or title must be provided or resolvable from item")

    # Resolve PDF URL through cascade
    await ctx.report_progress(progress=0, total=3)
    pdf_url, source = await resolver.resolve(effective_doi, effective_title)

    # Download and extract text
    await ctx.report_progress(progress=1, total=3)
    pdf_bytes = await resolver.download(pdf_url)

    await ctx.report_progress(progress=2, total=3)
    text = resolver.extract_text(pdf_bytes)
    await ctx.report_progress(progress=3, total=3)

    if not text.strip():
        return ExternalFulltextResponse(
            item_key=item_key,
            content="",
            source=source,
            error="PDF downloaded but no text could be extracted",
        ).to_slim_dict()  # type: ignore[return-value]

    # Attach PDF to Zotero item if item_key provided
    pdf_attached = False
    if item_key:
        pdf_attached = await _attach_pdf_to_item(ctx, item_key, pdf_bytes)

    # Chunk if needed (reuse existing TextChunker + get_next_fulltext_chunk)
    chunk_key = item_key or effective_doi or effective_title or "external"
    if not text_chunker.needs_chunking(text):
        return ExternalFulltextResponse(
            item_key=item_key,
            content=text,
            source=source,
            pdf_attached=pdf_attached,
        ).to_slim_dict()  # type: ignore[return-value]

    chunk_data = text_chunker.chunk_text(text, chunk_key)
    message = None
    if chunk_data.has_more:
        message = (
            f"Fulltext chunked ({chunk_data.chunk_info}). "
            f"To get remaining text, call: "
            f"get_next_fulltext_chunk(chunk_id='{chunk_data.chunk_id}')"
        )

    return ExternalFulltextResponse(
        item_key=item_key,
        content=chunk_data.content,
        source=source,
        pdf_attached=pdf_attached,
        has_more=chunk_data.has_more,
        chunk_id=chunk_data.chunk_id,
        current_chunk=chunk_data.current_chunk,
        total_chunks=chunk_data.total_chunks,
        message=message,
    ).to_slim_dict()  # type: ignore[return-value]


async def _attach_pdf_to_item(ctx: Context, item_key: str, pdf_bytes: bytes) -> bool:
    """Attempt to attach PDF to a Zotero item. Returns True if successful."""
    router: ZoteroClientRouter = _deps(ctx)["router"]
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp_path = f.name
        try:
            await router.attach_pdf(item_key, tmp_path)
            return True
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.warning("PDF attachment failed for item %s: %s", item_key, e)
        return False


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
async def remove_item(
    item_key: str,
    ctx: Context,
    collection_key: str | None = None,
    from_library: bool = False,
) -> dict[str, Any]:
    """
    Remove an item from a collection or delete it from the library entirely.

    Smart behavior when collection_key is provided and from_library is False:
    - If the item belongs to only one collection, it is deleted from the library entirely
    - If the item belongs to multiple collections, it is only removed from the specified collection

    Args:
        item_key: The Zotero item key to remove
        collection_key: Collection to remove the item from (optional)
        from_library: If True, force deletion from library regardless of collection membership

    Returns:
        Dictionary describing the action taken

    Examples:
        # Smart removal from collection (deletes from library if only in this collection)
        remove_item(item_key="ABC123", collection_key="COL456")

        # Force delete from library
        remove_item(item_key="ABC123", from_library=True)
    """
    router: ZoteroClientRouter = _deps(ctx)["router"]

    if collection_key is None and not from_library:
        raise ZoteroError(
            "Specify collection_key to remove from collection, "
            "or set from_library=True to delete from library entirely."
        )

    if from_library:
        await router.delete_item_by_key(item_key)
        return {"action": "deleted_from_library", "item_key": item_key}

    # collection_key is guaranteed to be str here (None case handled above)
    # narrow type for mypy
    collection_key_str: str = collection_key  # type: ignore[assignment]

    item = await router.get_item(item_key)

    if collection_key_str not in item.data.collections:
        raise ZoteroNotFoundError(
            "item in collection",
            f"item {item_key} is not in collection {collection_key_str}",
        )

    if len(item.data.collections) <= 1:
        await router.delete_item(item)
        return {
            "action": "deleted_from_library",
            "item_key": item_key,
            "reason": "item was only in this collection",
        }

    await router.remove_from_collection(collection_key_str, item_key)
    return {
        "action": "removed_from_collection",
        "item_key": item_key,
        "collection_key": collection_key_str,
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True))
async def update_item_tags(
    item_key: str,
    tags: list[str],
    ctx: Context,
    mode: Literal["add", "remove", "replace"] = "add",
) -> dict[str, Any]:
    """
    Add, remove, or replace tags on a Zotero item.

    Manages tags on an existing item with three modes:
    - 'add' (default): append tags to existing ones, duplicates are ignored
    - 'remove': remove specified tags, missing tags are silently ignored
    - 'replace': replace all tags with the provided list, empty list clears all tags

    New tags are created with type=1 (manual/user-created).
    Existing tags preserve their original type.

    Args:
        item_key: The Zotero item key to update tags on
        tags: List of tag names to add, remove, or set
        mode: Operation mode — 'add', 'remove', or 'replace' (default: 'add')

    Returns:
        Dictionary with item_key, mode, tags_before, tags_after, and changed flag

    Examples:
        # Add tags to an item
        update_item_tags(item_key="ABC123", tags=["important", "to-read"])

        # Remove specific tags
        update_item_tags(item_key="ABC123", tags=["to-read"], mode="remove")

        # Replace all tags
        update_item_tags(item_key="ABC123", tags=["reviewed"], mode="replace")

        # Clear all tags
        update_item_tags(item_key="ABC123", tags=[], mode="replace")
    """
    router: ZoteroClientRouter = _deps(ctx)["router"]

    item = await router.get_item(item_key)
    existing_tags = item.data.tags
    tags_before = [t.tag for t in existing_tags]

    if mode == "replace":
        new_tags = [ZoteroTag(tag=t, type=1) for t in tags]
    elif mode == "add":
        existing_names: set[str] = set()
        new_tags = []
        for existing in existing_tags:
            if existing.tag not in existing_names:
                existing_names.add(existing.tag)
                new_tags.append(existing)
        for tag_name in tags:
            if tag_name not in existing_names:
                new_tags.append(ZoteroTag(tag=tag_name, type=1))
                existing_names.add(tag_name)
    elif mode == "remove":
        remove_set = set(tags)
        new_tags = [t for t in existing_tags if t.tag not in remove_set]
    else:
        raise ZoteroError(f"Invalid mode: {mode!r}. Use 'add', 'remove', or 'replace'.")

    tags_after = [t.tag for t in new_tags]

    if tags_before == tags_after:
        return {
            "item_key": item_key,
            "mode": mode,
            "tags_before": tags_before,
            "tags_after": tags_after,
            "changed": False,
        }

    await router.update_item(item_key, ItemUpdate(tags=new_tags))

    return {
        "item_key": item_key,
        "mode": mode,
        "tags_before": tags_before,
        "tags_after": tags_after,
        "changed": True,
    }


@mcp.resource("resource://collections")
async def list_collections(ctx: Context) -> str:
    """List available Zotero collections."""
    router: ZoteroClientRouter = _deps(ctx)["router"]
    collections = await router.get_collections()

    if not collections:
        return "No collections found in library"

    result = "Available Collections:\n\n"
    for coll in collections:
        parent_info = ""
        if coll.parent_collection:
            parent_info = f", parent: {coll.parent_collection}"
        result += f"- {coll.name} (key: {coll.key}, items: {coll.num_items}{parent_info})\n"

    return result


if __name__ == "__main__":
    mcp.run()
