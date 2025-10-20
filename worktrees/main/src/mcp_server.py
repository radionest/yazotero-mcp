from fastmcp import Context, FastMCP

from .chunker import ResponseChunker
from .models import (
    AnalysisType,
    AnalyzeFulltextRequest,
    AnalyzeFulltextResponse,
    ManageNotesRequest,
    ManageNotesResponse,
    MethodsAnalysis,
    NoteAction,
    SearchCollectionRequest,
    SearchCollectionResponse,
    TextSummary,
)
from .note_manager import NoteManager
from .text_analyzer import TextAnalyzer
from .zotero_client import ZoteroClient

# Initialize components
_client: ZoteroClient | None = None
_chunker: ResponseChunker = ResponseChunker()


def get_client() -> ZoteroClient:
    """Get or create Zotero client singleton."""
    global _client
    if _client is None:
        _client = ZoteroClient()
    return _client


# Create FastMCP server
mcp: FastMCP = FastMCP("zotero-mcp")


@mcp.tool()
async def search_collection(
    ctx: Context, request: SearchCollectionRequest
) -> SearchCollectionResponse:
    """
    Search and evaluate items in a specific collection.
    Returns items with abstracts and metadata for assessment.
    """
    client = get_client()

    # Get collection items
    items = await client.get_collection_items(request.collection_key)

    # Filter by query if provided
    if request.query:
        query_lower = request.query.lower()
        filtered_items = []
        for item in items:
            if (
                query_lower in item.title.lower()
                or query_lower in item.abstract.lower()
                or any(query_lower in tag.lower() for tag in item.tags)
            ):
                filtered_items.append(item)
        items = filtered_items

    # Include full text if requested
    if request.include_fulltext:
        for item in items:
            item.fulltext = await client.get_fulltext(item.key)

    # Chunk if needed
    if _chunker.needs_chunking(items):
        chunk_response = _chunker.chunk_response(items)
        return SearchCollectionResponse(
            items=chunk_response.items,
            count=len(items),  # Total count before chunking
            has_more=chunk_response.has_more,
            chunk_id=chunk_response.chunk_id,
            chunk_info=chunk_response.chunk_info,
        )

    return SearchCollectionResponse(items=items, count=len(items))


@mcp.tool()
async def analyze_fulltext(
    ctx: Context, request: AnalyzeFulltextRequest
) -> AnalyzeFulltextResponse:
    """
    Analyze full text of an article for research evaluation.
    """
    client = get_client()

    # Get item and full text
    item = await client.get_item(request.item_key)
    fulltext = await client.get_fulltext(request.item_key)

    if not fulltext:
        return AnalyzeFulltextResponse(
            item_key=request.item_key,
            title=item.title,
            analysis_type=request.analysis_type,
            result=[],
            error="No full text available",
        )

    # Perform analysis
    analyzer = TextAnalyzer()

    result: TextSummary | list[str] | MethodsAnalysis
    if request.analysis_type == AnalysisType.SUMMARY:
        result = analyzer.summarize(fulltext, item.abstract)
    elif request.analysis_type == AnalysisType.KEY_POINTS:
        result = analyzer.extract_key_points(fulltext)
    elif request.analysis_type == AnalysisType.METHODS:
        result = analyzer.extract_methods(fulltext)
    else:
        result = analyzer.basic_analysis(fulltext)

    return AnalyzeFulltextResponse(
        item_key=request.item_key,
        title=item.title,
        analysis_type=request.analysis_type,
        result=result,
    )


@mcp.tool()
async def manage_notes(ctx: Context, request: ManageNotesRequest) -> ManageNotesResponse:
    """
    Complete note management for research annotations.
    """
    client = get_client()
    note_manager = NoteManager(client)

    if request.action == NoteAction.CREATE:
        if not request.item_key or not request.content:
            return ManageNotesResponse(error="item_key and content required")
        note = await note_manager.create_note(request.item_key, request.content)
        return ManageNotesResponse(note=note)

    elif request.action == NoteAction.READ:
        if request.note_key:
            note = await note_manager.get_note(request.note_key)
            return ManageNotesResponse(note=note)
        elif request.item_key:
            notes = await note_manager.get_notes_for_item(request.item_key)
            return ManageNotesResponse(notes=notes, count=len(notes))
        else:
            return ManageNotesResponse(error="note_key or item_key required")

    elif request.action == NoteAction.UPDATE:
        if not request.note_key or not request.content:
            return ManageNotesResponse(error="note_key and content required")
        note = await note_manager.update_note(request.note_key, request.content)
        return ManageNotesResponse(note=note)

    elif request.action == NoteAction.SEARCH:
        if not request.search_query:
            return ManageNotesResponse(error="search_query required")
        notes = await note_manager.search_notes(request.search_query)
        return ManageNotesResponse(notes=notes, count=len(notes))

    return ManageNotesResponse(error="Invalid action")


@mcp.tool()
async def get_next_chunk(ctx: Context, chunk_id: str) -> SearchCollectionResponse:
    """
    Get next chunk of search results.
    """
    chunk_response = _chunker.get_next_chunk(chunk_id)

    if chunk_response.error:
        return SearchCollectionResponse(items=[], count=0, error=chunk_response.error)

    return SearchCollectionResponse(
        items=chunk_response.items,
        count=len(chunk_response.items),
        has_more=chunk_response.has_more,
        chunk_id=chunk_response.chunk_id,
        chunk_info=chunk_response.chunk_info,
    )


@mcp.resource("zotero://collections")
async def list_collections(ctx: Context) -> str:
    """List available Zotero collections."""
    # This would require additional Zotero API calls
    # For now, return placeholder
    return "Collections resource not yet implemented"


@mcp.resource("zotero://tags")
async def list_tags(ctx: Context) -> str:
    """List available tags in Zotero library."""
    # This would require additional Zotero API calls
    # For now, return placeholder
    return "Tags resource not yet implemented"


if __name__ == "__main__":
    mcp.run()
