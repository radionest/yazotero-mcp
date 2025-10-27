from typing import Any

from fastmcp import FastMCP

from .chunker import ResponseChunker, TextChunker
from .models import (
    FulltextResponse,
    Note,
    SearchCollectionResponse,
    ZoteroItem,
)
from .note_manager import NoteManager
from .zotero_client import zotero_client

# Initialize components
_chunker: ResponseChunker = ResponseChunker()
_text_chunker: TextChunker = TextChunker()
_note_manager = NoteManager(zotero_client)


# Create FastMCP server
mcp: FastMCP = FastMCP("zotero-mcp")


@mcp.tool
async def get_collection_items(collection_key: str) -> SearchCollectionResponse:
    """
    Search and evaluate items in a specific collection.
    Returns items with abstracts and metadata for assessment.

    Args:
        collection_key: The collection key to retrieve items from

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
    # Get collection items
    collection = await zotero_client.get_collection(key=collection_key)
    filtered_items = collection.items.all()

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
    """
    chunk_response = _chunker.get_next_chunk(chunk_id)

    if chunk_response.error:
        return SearchCollectionResponse(items=[], count=0, error=chunk_response.error)

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

    # Execute search
    if collection_key:
        # Search within specific collection
        collection = await zotero_client.get_collection(key=collection_key)
        # Get items using iterator and apply filters
        all_items = collection.items.all()
        filtered_items = all_items
    else:
        # Search across entire library
        # Use pyzotero's items() method with search parameters
        raw_items = zotero_client._client.items(**search_params)
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
async def get_item_fulltext(item_key: str) -> FulltextResponse:
    """
    Get full text content for a Zotero item (e.g., from PDF attachment).

    Returns the text content with automatic chunking if the text is too large
    to fit in a single response. Use this endpoint instead of include_fulltext
    parameter in other endpoints.

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
    # Get fulltext from Zotero
    fulltext = await zotero_client.get_fulltext(item_key)

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

    Example:
        # After getting initial fulltext with has_more=True
        next_chunk = get_next_fulltext_chunk(chunk_id="uuid-here")
    """
    chunk_data = _text_chunker.get_next_text_chunk(chunk_id)

    if chunk_data.get("error"):
        return FulltextResponse(
            item_key="",
            content="",
            has_more=False,
            error=chunk_data["error"],
        )

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
    collections = zotero_client.collections

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


if __name__ == "__main__":
    mcp.run()
