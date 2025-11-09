from typing import Any

from fastmcp import Context, FastMCP

from src.exceptions import ZoteroNotFoundError
from src.protocols import ZoteroClientProtocol

from .chunker import ResponseChunker, TextChunker
from .client_router import client_router
from .crossref_client import crossref_client
from .models import (
    CollectionCreate,
    FulltextResponse,
    Note,
    SearchCollectionResponse,
    ZoteroItem,
)
from .note_manager import NoteManager
from .zotero_client import Collection

# Initialize components
_chunker: ResponseChunker = ResponseChunker()
_text_chunker: TextChunker = TextChunker()
# Use router directly as client for note manager (implements ZoteroClientProtocol)
_zotero_client: ZoteroClientProtocol = client_router
_note_manager = NoteManager(_zotero_client)


# Create FastMCP server with error masking for security
# Custom exceptions (ToolError subclasses) will still show details to clients
mcp: FastMCP = FastMCP("zotero-mcp", mask_error_details=True)


@mcp.tool
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
    # Use router directly (implements protocol with fallback)

    collection = await _zotero_client.get_collection(key=collection_key)
    # Helper function to recursively collect items from subcollections
    if not collection:
        raise ZoteroNotFoundError("collection", collection_key)

    def collect_items_recursive(coll: Collection) -> list[ZoteroItem]:
        items = coll.items.all()
        if include_subcollections:
            for subcoll in coll.subcollections:
                items.extend(collect_items_recursive(subcoll))
        return items

    # Collect items (with or without subcollections)
    filtered_items = collect_items_recursive(collection)

    # Remove duplicates by key (items can appear in multiple collections)
    seen_keys = set()
    unique_items = []
    for item in filtered_items:
        if item.key not in seen_keys:
            seen_keys.add(item.key)
            unique_items.append(item)

    filtered_items = unique_items
    await ctx.debug("\n".join([str(i) for i in filtered_items]))

    # Chunk if needed
    if _chunker.needs_chunking(filtered_items):
        chunk_response = _chunker.chunk_response(filtered_items)
        return SearchCollectionResponse(
            items=chunk_response.items,
            count=len(filtered_items),  # Total count before chunking
            has_more=chunk_response.has_more,
            chunk_id=chunk_response.chunk_id,
            current_chunk=chunk_response.current_chunk,
            total_chunks=chunk_response.total_chunks,
            message=(
                f"⚠️ Results chunked ({chunk_response.chunk_info}). "
                f"To get remaining results, call: get_next_chunk(chunk_id='{chunk_response.chunk_id}')"
            ),
        )

    return SearchCollectionResponse(items=filtered_items, count=len(filtered_items))


@mcp.tool
async def get_next_chunk(chunk_id: str) -> SearchCollectionResponse:
    """
    Get next chunk of search results.

    Use this tool when 'search_collection' returns 'has_more=True'.
    Pass the 'chunk_id' from the previous response to retrieve the next batch of items.
    Continue calling until 'has_more=False' to get all results.

    Raises:
        ZoteroNotFoundError: If chunk_id is invalid or expired
    """
    chunk_response = _chunker.get_next_chunk(chunk_id)

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
    )


@mcp.tool
async def search_articles(
    query: str | None = None,
    tags: list[str] | None = None,
    collection_key: str | None = None,
    item_type: str | None = None,
) -> SearchCollectionResponse:
    """
    Search for articles by name, tags, collections, or item type.

    Supports flexible searching across your Zotero library with multiple filter options.

    Args:
        query: Quick search string to match against titles and creators (optional)
        tags: List of tags to filter by - items must have ALL listed tags (optional)
        collection_key: Filter by specific collection key (optional)
        item_type: Filter by item type (e.g., 'journalArticle', 'book', 'conferencePaper') (optional)

    Returns:
        SearchCollectionResponse with matching items

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
    # Build search parameters
    search_params: dict[str, Any] = {}

    if query:
        search_params["q"] = query
        search_params["qmode"] = "titleCreatorYear"

    if item_type:
        search_params["itemType"] = item_type

    if tags:
        # Multiple tags create AND logic in Zotero API
        search_params["tag"] = tags

    # Execute search using router (implements protocol with fallback)
    if collection_key:
        # Search within specific collection
        collection = await _zotero_client.get_collection(key=collection_key)
        # Get items using iterator and apply filters
        if not collection:
            raise ZoteroNotFoundError("collection", collection_key)
        all_items = collection.items.all()
        filtered_items = all_items
    else:
        # Search across entire library
        # Use pyzotero's items() method with search parameters
        # Access underlying client via read_client for direct pyzotero access
        raise NotImplementedError
        raw_items = _zotero_client.items
        filtered_items = [ZoteroItem.model_validate(item) for item in raw_items]

    # Manual tag filtering if needed (pyzotero may not support all tag logic)
    if tags:
        filtered_items = [
            item for item in filtered_items if all(tag in item.tags() for tag in tags)
        ]

    # Chunk if needed
    if _chunker.needs_chunking(filtered_items):
        chunk_response = _chunker.chunk_response(filtered_items)
        return SearchCollectionResponse(
            items=chunk_response.items,
            count=len(filtered_items),  # Total count before chunking
            has_more=chunk_response.has_more,
            chunk_id=chunk_response.chunk_id,
            current_chunk=chunk_response.current_chunk,
            total_chunks=chunk_response.total_chunks,
            message=(
                f"⚠️ Results chunked ({chunk_response.chunk_info}). "
                f"To get remaining results, call: get_next_chunk(chunk_id='{chunk_response.chunk_id}')"
            ),
        )

    return SearchCollectionResponse(items=filtered_items, count=len(filtered_items))


@mcp.tool
async def create_note_for_item(
    item_key: str, title: str, content: str | dict[str, Any], tags: list[str] | None = None
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
    # Format content if it's a dict
    if isinstance(content, dict):
        import json

        formatted_content = f"# {title}\n\n{json.dumps(content, indent=2)}"
    else:
        formatted_content = f"# {title}\n\n{content}"

    note = await _note_manager.create_note(item_key=item_key, content=formatted_content, tags=tags)

    return note


@mcp.tool
async def get_item_notes(item_key: str) -> list[Note]:
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
    notes = await _note_manager.get_notes_for_item(item_key=item_key)
    return notes


@mcp.tool
async def create_collection(name: str, parent_collection_key: str | None = None) -> dict[str, Any]:
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
    # Create CollectionCreate model
    collection_data = CollectionCreate(name=name, parent_collection=parent_collection_key)

    # Use client_router which implements web-only operations
    created_collections = await _zotero_client.create_collections([collection_data])

    if not created_collections:
        return {"error": "Failed to create collection"}

    # Return the first (and only) created collection
    created = created_collections[0]
    return {
        "key": created.key,
        "name": created.name,
        "version": created.version,
        "parent_collection": parent_collection_key,
    }


@mcp.tool
async def add_item_by_doi(
    doi: str, collection_key: str | None = None, tags: list[str] | None = None
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

    Note:
        - This operation requires web API access with write permissions
        - DOI must be valid and exist in Crossref database
        - The item type (article, book, etc.) is automatically determined from metadata
        - If collection_key is provided, the item is automatically added to that collection

    Examples:
        # Add article by DOI
        item = add_item_by_doi("10.1038/nature12373")

        # Add to specific collection with tags
        item = add_item_by_doi(
            doi="10.1038/nature12373",
            collection_key="ABC123XYZ",
            tags=["important", "to-read"]
        )
    """
    # Fetch metadata from Crossref
    crossref_metadata = await crossref_client.get_metadata_by_doi(doi)

    # Convert to Zotero format (returns ItemCreate)
    item_create = crossref_client.crossref_to_zotero(crossref_metadata)

    # Add tags if provided
    if tags:
        from .models import ZoteroTag

        item_create.tags = [ZoteroTag(tag=tag) for tag in tags]

    # Add collection if provided
    if collection_key:
        # ItemCreate supports extra fields via model_config
        item_create.collections = [collection_key]

    # Create item in Zotero
    created_items = await _zotero_client.create_items([item_create])

    if not created_items:
        from .exceptions import ZoteroWriteError

        raise ZoteroWriteError("add_item_by_doi", {"error": "Failed to create item from DOI"})

    return created_items[0]


@mcp.tool
async def get_item_fulltext(item_key: str) -> FulltextResponse:
    """
    Get full text content for a Zotero item (e.g., from PDF attachment).

    Returns the text content with automatic chunking if the text is too large
    to fit in a single response. Use this endpoint instead of include_fulltext
    parameter in other endpoints.

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

    Example:
        # Get fulltext for an item
        result = get_item_fulltext("ABC123XYZ")

        # If chunked, get remaining parts
        if result.has_more:
            next_part = get_next_fulltext_chunk(result.chunk_id)
    """
    # Use router with automatic fallback (local->web)
    # Try Zotero's pre-indexed fulltext API first (fast)
    fulltext = await _zotero_client.get_fulltext(item_key)

    # If unavailable, fallback to direct PDF parsing
    if not fulltext:
        fulltext = await _zotero_client.get_pdf_text(item_key)

    if not fulltext:
        return FulltextResponse(
            item_key=item_key,
            content="",
            has_more=False,
            error="No fulltext available for this item",
        )

    # Check if chunking is needed
    if not _text_chunker.needs_chunking(fulltext):
        return FulltextResponse(
            item_key=item_key,
            content=fulltext,
            has_more=False,
        )

    # Chunk the text
    chunk_data = _text_chunker.chunk_text(fulltext, item_key)

    message = None
    if chunk_data["has_more"]:
        message = (
            f"⚠️ Fulltext chunked ({chunk_data['current_chunk']}/{chunk_data['total_chunks']}). "
            f"To get remaining text, call: get_next_fulltext_chunk(chunk_id='{chunk_data['chunk_id']}')"
        )

    return FulltextResponse(
        item_key=chunk_data["item_key"],
        content=chunk_data["content"],
        has_more=chunk_data["has_more"],
        chunk_id=chunk_data["chunk_id"],
        current_chunk=chunk_data["current_chunk"],
        total_chunks=chunk_data["total_chunks"],
        message=message,
    )


@mcp.tool
async def get_next_fulltext_chunk(chunk_id: str) -> FulltextResponse:
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

    Example:
        # After getting initial fulltext with has_more=True
        next_chunk = get_next_fulltext_chunk(chunk_id="uuid-here")
    """
    chunk_data = _text_chunker.get_next_text_chunk(chunk_id)

    message = None
    if chunk_data["has_more"]:
        message = (
            f"⚠️ More text available ({chunk_data['current_chunk']}/{chunk_data['total_chunks']}). "
            f"Call: get_next_fulltext_chunk(chunk_id='{chunk_data['chunk_id']}')"
        )
    else:
        if chunk_data["current_chunk"] and chunk_data["total_chunks"]:
            message = f"✓ All text retrieved ({chunk_data['current_chunk']}/{chunk_data['total_chunks']})."

    return FulltextResponse(
        item_key=chunk_data["item_key"],
        content=chunk_data["content"],
        has_more=chunk_data["has_more"],
        chunk_id=chunk_data["chunk_id"],
        current_chunk=chunk_data["current_chunk"],
        total_chunks=chunk_data["total_chunks"],
        message=message,
    )


@mcp.resource("resource://collections")
async def list_collections() -> str:
    """List available Zotero collections."""
    # Use router directly (implements protocol with fallback)
    collections = _zotero_client.collections

    if not collections:
        return "No collections found in library"

    result = "Available Collections:\n\n"
    for coll in collections:
        result += f"- {coll.name} (key: {coll.key})\n"

    return result


@mcp.resource("resource://tags")
async def list_tags() -> str:
    """List available tags in Zotero library."""
    # This would require additional Zotero API calls
    # For now, return placeholder
    return "Tags resource not yet implemented"


@mcp.prompt()
def zotero_usage_guide() -> str:
    """
    Guide for using Zotero MCP server effectively.

    This prompt provides instructions for AI models on how to properly use
    this MCP server's tools and handle chunked responses.
    """
    return """# Zotero MCP Server Usage Guide

## Overview
This server provides access to Zotero library for searching articles, managing notes, and retrieving fulltext content.

## Important: Chunked Responses
Many tools return chunked data when responses are large. Always check for chunking:

### Response Chunking (for search results)
- If `has_more=True` in response, call `get_next_chunk(chunk_id)`
- Continue until `has_more=False`
- Check `current_chunk` and `total_chunks` for progress

### Fulltext Chunking (for article text)
- If `has_more=True` in fulltext response, call `get_next_fulltext_chunk(chunk_id)`
- Continue until `has_more=False`
- Text is split intelligently by paragraphs/sentences

## Workflow Examples

### 1. Search and Read Articles
```
1. Use search_articles() or get_collection_items()
2. If has_more=True, call get_next_chunk() until complete
3. For specific item, call get_item_fulltext(item_key)
4. If fulltext has_more=True, call get_next_fulltext_chunk() until complete
```

### 2. Create Notes
```
1. Find item using search_articles()
2. Call create_note_for_item(item_key, title, content, tags)
```

## Available Tools
- **search_articles**: Search by query, tags, collection, or item type
- **get_collection_items**: Get all items from specific collection
- **get_item_fulltext**: Retrieve full text (with automatic chunking)
- **create_note_for_item**: Create notes attached to items
- **get_next_chunk**: Get next batch of search results
- **get_next_fulltext_chunk**: Get next part of fulltext

## Available Resources
- **resource://collections**: List all available collections
- **resource://tags**: List tags (not yet implemented)

## Best Practices
1. Always handle chunked responses completely before proceeding
2. Use tags for filtering and organization
3. Check error fields in responses
4. Use get_item_fulltext separately instead of including in search
"""


if __name__ == "__main__":
    mcp.run()
