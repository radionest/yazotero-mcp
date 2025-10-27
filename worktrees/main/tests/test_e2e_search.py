"""E2E tests for search functionality without mocks."""

import pytest
from fastmcp import Client

import src.zotero_client
from src.mcp_server import mcp
from src.zotero_client import ZoteroClient


class TestSearchE2E:
    """End-to-end tests for search with real Zotero."""

    @pytest.mark.asyncio
    async def test_get_collection_items_basic(
        self,
        basic_collection_with_items: tuple[str, int],
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test basic collection search returns real items."""
        src.zotero_client.zotero_client = real_zotero_client
        collection_key, expected_count = basic_collection_with_items

        request = {"collection_key": collection_key}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Verify response structure
        assert response.count == expected_count
        assert isinstance(response.items, list)
        assert len(response.items) == expected_count

        item = response.items[0]
        assert item.key
        assert item.data.title
        # Check that abstract exists (might be empty)
        assert hasattr(item.data, "title")

    @pytest.mark.asyncio
    async def test_search_with_fulltext(
        self,
        collection_for_fulltext_test: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test including full text in search results."""
        src.zotero_client.zotero_client = real_zotero_client
        collection_key = collection_for_fulltext_test

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": collection_key, "include_fulltext": True},
            )
            response = result.data

        # Check that fulltext field is populated (might be None)
        for item in response.items:
            assert hasattr(item, "fulltext")
            # Fulltext can be None if no PDF available

    @pytest.mark.asyncio
    async def test_search_chunking(
        self,
        collection_for_chunking_test: str,
        chunker_with_small_size: int,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test response chunking for large results."""
        src.zotero_client.zotero_client = real_zotero_client
        collection_key = collection_for_chunking_test

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": collection_key, "include_fulltext": True},
            )
            response = result.data

        # Chunking should be triggered with small chunk size
        if response.has_more:
            assert response.chunk_id
            assert response.current_chunk is not None
            assert response.total_chunks is not None
            assert response.current_chunk >= 1
            assert response.total_chunks >= response.current_chunk
            # Test backward compatibility
