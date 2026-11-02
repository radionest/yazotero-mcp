"""Tests for get_collection_items with include_subcollections parameter."""

import logging
from collections import Counter

import pytest
from fastmcp import Client

from tests.e2e.conftest import parse_tool_result
from yazot.mcp_server import mcp
from yazot.models import SearchCollectionResponse
from yazot.zotero_client import ZoteroClient

logger = logging.getLogger(__name__)


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
            response = parse_tool_result(result, SearchCollectionResponse)

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
            response = parse_tool_result(result, SearchCollectionResponse)

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
            response = parse_tool_result(result, SearchCollectionResponse)

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
            response = parse_tool_result(result, SearchCollectionResponse)

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
            response = parse_tool_result(result, SearchCollectionResponse)

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
            response = parse_tool_result(result, SearchCollectionResponse)

        # Should return only items from parent (subcollections are empty)
        assert response.count == expected_count
        assert len(response.items) == expected_count

    @pytest.mark.asyncio
    async def test_subcollections_with_chunking(
        self,
        large_nested_collection: tuple[str, int, dict[str, set[str]]],
        chunker_with_small_size: int,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test chunking and log enough state to localize any missing items."""
        parent_key, expected_total, expected_by_collection = large_nested_collection
        expected_keys = {
            item_key
            for collection_keys in expected_by_collection.values()
            for item_key in collection_keys
        }

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": parent_key, "include_subcollections": True},
            )
            response = parse_tool_result(result, SearchCollectionResponse)
            initial_count = response.count
            chunking_triggered = response.has_more

            if chunking_triggered:
                assert response.chunk_id
                assert response.current_chunk is not None
                assert response.total_chunks is not None

            all_items = list(response.items)
            while response.has_more:
                result = await client.call_tool(
                    "get_next_chunk", arguments={"chunk_id": response.chunk_id}
                )
                response = parse_tool_result(result, SearchCollectionResponse)
                all_items.extend(response.items)

        received_keys = [item.key for item in all_items]
        received_key_set = set(received_keys)
        missing_keys = sorted(expected_keys - received_key_set)
        unexpected_keys = sorted(received_key_set - expected_keys)
        duplicate_keys = sorted(
            item_key for item_key, count in Counter(received_keys).items() if count > 1
        )
        mismatch = (
            len(expected_keys) != expected_total
            or initial_count != expected_total
            or len(all_items) != expected_total
            or received_key_set != expected_keys
            or bool(duplicate_keys)
        )

        if mismatch:
            logger.error(
                "Issue #62 response mismatch: parent=%s initial_count=%d received=%d "
                "unique_received=%d expected=%d fixture_keys=%d missing=%s "
                "unexpected=%s duplicates=%s",
                parent_key,
                initial_count,
                len(received_keys),
                len(received_key_set),
                expected_total,
                len(expected_keys),
                missing_keys,
                unexpected_keys,
                duplicate_keys,
            )

            for collection_key, expected_collection_keys in expected_by_collection.items():
                try:
                    collection = await test_zotero_client.get_collection(key=collection_key)
                    if collection is None:
                        logger.error(
                            "Issue #62 collection lookup returned None: collection=%s",
                            collection_key,
                        )
                        continue
                    direct_items = await collection.get_items()
                except Exception:
                    logger.exception(
                        "Issue #62 direct collection read failed: collection=%s",
                        collection_key,
                    )
                    continue

                direct_keys = {item.key for item in direct_items}
                logger.error(
                    "Issue #62 direct collection state: collection=%s expected=%d "
                    "received=%d unique_received=%d missing=%s unexpected=%s",
                    collection_key,
                    len(expected_collection_keys),
                    len(direct_items),
                    len(direct_keys),
                    sorted(expected_collection_keys - direct_keys),
                    sorted(direct_keys - expected_collection_keys),
                )

            for item_key in missing_keys:
                try:
                    raw_item = await test_zotero_client.get_raw_item(item_key)
                except Exception:
                    logger.exception("Issue #62 missing item read failed: item=%s", item_key)
                    continue

                item_data = raw_item.get("data", {})
                logger.error(
                    "Issue #62 missing item state: item=%s version=%s collections=%s deleted=%s",
                    item_key,
                    raw_item.get("version"),
                    item_data.get("collections"),
                    item_data.get("deleted"),
                )

        assert chunking_triggered, "Small MAX_CHUNK_SIZE must force chunking"
        assert initial_count == expected_total
        assert len(all_items) == expected_total
        assert not duplicate_keys, f"Duplicate items found across chunks: {duplicate_keys}"
        assert received_key_set == expected_keys
