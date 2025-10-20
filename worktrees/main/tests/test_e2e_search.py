"""E2E tests for search functionality without mocks."""

import pytest
from fastmcp import Context

from src.mcp_server import search_collection
from src.models import SearchCollectionRequest
from src.zotero_client import ZoteroClient


class TestSearchE2E:
    """End-to-end tests for search with real Zotero."""
    
    @pytest.mark.asyncio
    async def test_search_collection_basic(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test basic collection search returns real items."""
        # Override global client
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        request = SearchCollectionRequest(
            collection_key=test_collection_key,
            include_fulltext=False,
        )
        
        response = await search_collection(mcp_context, request)
        
        # Verify response structure
        assert response.count >= 0
        assert isinstance(response.items, list)
        
        if response.items:
            item = response.items[0]
            assert item.key
            assert item.title
            # Check that abstract exists (might be empty)
            assert hasattr(item, "abstract")
    
    @pytest.mark.asyncio
    async def test_search_with_query_filter(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test search filters results by query."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # First get all items
        all_request = SearchCollectionRequest(
            collection_key=test_collection_key,
        )
        all_response = await search_collection(mcp_context, all_request)
        
        if not all_response.items:
            pytest.skip("No items in test collection")
        
        # Search with specific term from first item
        first_item = all_response.items[0]
        search_term = first_item.title.split()[0] if first_item.title else "test"
        
        filtered_request = SearchCollectionRequest(
            collection_key=test_collection_key,
            query=search_term,
        )
        filtered_response = await search_collection(mcp_context, filtered_request)
        
        # Should have fewer or equal items
        assert filtered_response.count <= all_response.count
        
        # All returned items should match query
        for item in filtered_response.items:
            matches = (
                search_term.lower() in item.title.lower()
                or search_term.lower() in item.abstract.lower()
                or any(search_term.lower() in tag.lower() for tag in item.tags)
            )
            assert matches, f"Item {item.key} doesn't match query {search_term}"
    
    @pytest.mark.asyncio
    async def test_search_with_fulltext(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test including full text in search results."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        request = SearchCollectionRequest(
            collection_key=test_collection_key,
            include_fulltext=True,
        )
        
        response = await search_collection(mcp_context, request)
        
        # Check that fulltext field is populated (might be None)
        if response.items:
            for item in response.items:
                assert hasattr(item, "fulltext")
                # Fulltext can be None if no PDF available
    
    @pytest.mark.asyncio
    async def test_search_chunking(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test response chunking for large results."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Set very small chunk size to force chunking
        src.mcp_server._chunker.max_size = 100
        
        request = SearchCollectionRequest(
            collection_key=test_collection_key,
        )
        
        response = await search_collection(mcp_context, request)
        
        # If we have items and chunking is triggered
        if response.items and response.has_more:
            assert response.chunk_id
            assert response.chunk_info
            assert "chunk" in response.chunk_info.lower()
        
        # Restore default chunk size
        src.mcp_server._chunker.max_size = 20000
    
    @pytest.mark.asyncio
    async def test_cache_behavior(
        self,
        mcp_context: Context,
        test_collection_key: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that cache is used for repeated requests."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        request = SearchCollectionRequest(
            collection_key=test_collection_key,
        )
        
        # Clear cache first
        real_zotero_client.cache.clear()
        
        # First request - should populate cache
        response1 = await search_collection(mcp_context, request)
        cache_key = f"collection:{test_collection_key}"
        assert cache_key in real_zotero_client.cache
        
        # Second request - should use cache
        response2 = await search_collection(mcp_context, request)
        
        # Results should be identical
        assert response1.count == response2.count
        assert len(response1.items) == len(response2.items)
        if response1.items:
            assert response1.items[0].key == response2.items[0].key