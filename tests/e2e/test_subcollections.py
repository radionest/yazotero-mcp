"""Tests for get_collection_items with include_subcollections parameter."""

import pytest
from fastmcp import Client

from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient


class TestSubcollections:
    """Tests for subcollection functionality."""

    @pytest.mark.asyncio
    async def test_collection_without_subcollections(
        self,
        basic_collection_with_items: tuple[str, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that include_subcollections=False returns only items from main collection."""
        collection_key, expected_count = basic_collection_with_items

        request = {"collection_key": collection_key, "include_subcollections": False}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Should return only items from main collection
        assert response.count == expected_count
        assert len(response.items) == expected_count

    @pytest.mark.asyncio
    async def test_collection_with_subcollections_disabled(
        self,
        nested_collection_with_items: tuple[str, int, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that default behavior (include_subcollections=False) excludes subcollection items."""
        parent_key, parent_count, _ = nested_collection_with_items

        request = {"collection_key": parent_key}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Should return only items from parent collection
        assert response.count == parent_count
        assert len(response.items) == parent_count

    @pytest.mark.asyncio
    async def test_collection_with_subcollections_enabled(
        self,
        nested_collection_with_items: tuple[str, int, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that include_subcollections=True returns items from parent and all subcollections."""
        parent_key, parent_count, total_count = nested_collection_with_items

        request = {"collection_key": parent_key, "include_subcollections": True}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Should return items from parent + all subcollections
        assert response.count == total_count
        assert len(response.items) == total_count

        # Verify all items have unique keys (deduplication works)
        item_keys = [item.key for item in response.items]
        assert len(item_keys) == len(set(item_keys)), "Duplicate items found in response"

    @pytest.mark.asyncio
    async def test_deeply_nested_collections(
        self,
        deeply_nested_collection: tuple[str, dict[str, int]],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test recursive collection traversal with deeply nested structure."""
        root_key, counts = deeply_nested_collection

        request = {"collection_key": root_key, "include_subcollections": True}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Total count should be sum of all levels
        expected_total = sum(counts.values())
        assert response.count == expected_total
        assert len(response.items) == expected_total

    @pytest.mark.asyncio
    async def test_deduplication_across_subcollections(
        self,
        collection_with_duplicate_items: tuple[str, int, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that items appearing in multiple subcollections are deduplicated."""
        parent_key, unique_count, duplicate_count = collection_with_duplicate_items

        request = {"collection_key": parent_key, "include_subcollections": True}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Should return only unique items
        assert response.count == unique_count
        assert len(response.items) == unique_count

        # Verify no duplicate keys
        item_keys = [item.key for item in response.items]
        assert len(item_keys) == len(set(item_keys)), "Duplicate items found in response"

    @pytest.mark.asyncio
    async def test_empty_subcollections(
        self,
        collection_with_empty_subcollections: tuple[str, int],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that empty subcollections don't break the recursive traversal."""
        parent_key, expected_count = collection_with_empty_subcollections

        request = {"collection_key": parent_key, "include_subcollections": True}

        async with Client(mcp) as client:
            result = await client.call_tool("get_collection_items", arguments=request)
            response = result.data

        # Should return only items from parent (subcollections are empty)
        assert response.count == expected_count
        assert len(response.items) == expected_count

    @pytest.mark.asyncio
    async def test_subcollections_with_chunking(
        self,
        large_nested_collection: tuple[str, int],
        chunker_with_small_size: int,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that chunking works correctly with subcollection items."""
        parent_key, expected_total = large_nested_collection

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": parent_key, "include_subcollections": True},
            )
            response = result.data

            # With small chunk size, chunking should be triggered
            if response.has_more:
                assert response.chunk_id
                assert response.current_chunk is not None
                assert response.total_chunks is not None

                # Collect all chunks
                all_items = list(response.items)
                chunk_id = response.chunk_id

                while response.has_more:
                    result = await client.call_tool(
                        "get_next_chunk", arguments={"chunk_id": chunk_id}
                    )
                    response = result.data
                    all_items.extend(response.items)
                    chunk_id = response.chunk_id

                # Total should match expected
                assert len(all_items) == expected_total
