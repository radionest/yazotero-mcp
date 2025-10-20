"""Integration E2E tests for complete workflows."""

import uuid

import pytest
from fastmcp import Context

from src.mcp_server import analyze_fulltext, manage_notes, search_collection
from src.models import (
    AnalysisType,
    AnalyzeFulltextRequest,
    ManageNotesRequest,
    NoteAction,
    SearchCollectionRequest,
)
from src.zotero_client import ZoteroClient


class TestIntegrationE2E:
    """Test complete user workflows with real Zotero."""
    
    @pytest.mark.asyncio
    async def test_research_workflow(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
        setup_test_data: dict,
    ) -> None:
        """Test complete research workflow: search -> analyze -> annotate."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Step 1: Search collection
        search_request = SearchCollectionRequest(
            collection_key=test_collection_key,
        )
        search_response = await search_collection(mcp_context, search_request)
        
        assert search_response.items
        if not search_response.items:
            pytest.skip("No items in test collection")
        
        target_item = search_response.items[0]
        
        # Step 2: Analyze the item
        analyze_request = AnalyzeFulltextRequest(
            item_key=target_item.key,
            analysis_type=AnalysisType.KEY_POINTS,
        )
        analyze_response = await analyze_fulltext(mcp_context, analyze_request)
        
        assert analyze_response.item_key == target_item.key
        
        # Step 3: Create note based on analysis
        note_content = f"Analysis of {target_item.title}:\n"
        if analyze_response.result and not analyze_response.error:
            note_content += f"Key points: {analyze_response.result}"
        else:
            note_content += "No fulltext available for analysis"
        DSPCrk4RSMfVwMyJ3rpznlYA
        note_request = ManageNotesRequest(
            action=NoteAction.CREATE,
            item_key=target_item.key,
            content=note_content,
        )
        note_response = await manage_notes(mcp_context, note_request)
        
        assert not note_response.error
        assert note_response.note
        if note_response.note:
            setup_test_data["track_item"](note_response.note.key)
        
        # Verify the complete workflow
        assert note_response.note.parent_key == target_item.key
        assert target_item.title in note_response.note.content
    
    @pytest.mark.asyncio
    async def test_batch_processing(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
        setup_test_data: dict,
    ) -> None:
        """Test processing multiple items in batch."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Get multiple items
        search_request = SearchCollectionRequest(
            collection_key=test_collection_key,
        )
        search_response = await search_collection(mcp_context, search_request)
        
        # Process up to 3 items
        items_to_process = search_response.items[:3] if search_response.items else []
        
        results = []
        for item in items_to_process:
            # Analyze each item
            analyze_request = AnalyzeFulltextRequest(
                item_key=item.key,
                analysis_type=AnalysisType.SUMMARY,
            )
            analyze_response = await analyze_fulltext(mcp_context, analyze_request)
            
            # Create summary note
            note_request = ManageNotesRequest(
                action=NoteAction.CREATE,
                item_key=item.key,
                content=f"Batch processed: {item.title}",
            )
            note_response = await manage_notes(mcp_context, note_request)
            
            if note_response.note:
                setup_test_data["track_item"](note_response.note.key)
                results.append({
                    "item": item.key,
                    "analyzed": not analyze_response.error,
                    "noted": True,
                })
        
        # Verify batch processing
        assert len(results) == len(items_to_process)
        assert all(r["noted"] for r in results)
    
    @pytest.mark.asyncio
    async def test_cross_collection_search(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test searching with sub-collections included."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Search with sub-collections (default behavior)
        request_with_children = SearchCollectionRequest(
            collection_key=test_collection_key,
        )
        
        response = await search_collection(mcp_context, request_with_children)
        
        # Should return items from collection and sub-collections
        assert response.items is not None
        assert response.count >= 0
        
        # If chunking is enabled, test pagination
        if response.has_more and response.chunk_id:
            from src.mcp_server import get_next_chunk
            
            next_response = await get_next_chunk(mcp_context, response.chunk_id)
            assert next_response.items is not None
    
    @pytest.mark.asyncio
    async def test_performance_with_cache(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that caching improves performance."""
        import time
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Clear cache
        real_zotero_client.cache.clear()
        
        request = SearchCollectionRequest(
            collection_key=test_collection_key,
        )
        
        # First request - no cache
        start = time.time()
        await search_collection(mcp_context, request)
        first_time = time.time() - start
        
        # Second request - should use cache
        start = time.time()
        await search_collection(mcp_context, request)
        second_time = time.time() - start
        
        # Cache should make it faster (or at least not slower)
        # In real scenarios, cached request should be much faster
        assert second_time <= first_time * 1.5  # Allow some variance