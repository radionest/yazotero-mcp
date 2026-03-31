"""E2E tests for Zotero tags functionality via MCP endpoints."""

import pytest
from fastmcp import Client

from yazot.mcp_server import mcp
from yazot.models import ZoteroItem
from yazot.zotero_client import ZoteroClient


class TestTagsE2E:
    """End-to-end tests for tags with real Zotero via MCP."""

    @pytest.mark.asyncio
    async def test_get_items_with_tags_via_mcp(
        self,
        collection_key_items_with_tags: str,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test reading items with tags through get_collection_items MCP endpoint."""

        # Get all items via MCP
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items", arguments={"collection_key": collection_key_items_with_tags}
            )
            test_items = result.data.items

        # Find our test items in the response
        test_item_keys = {item.key for item in test_items}

        assert len(test_item_keys) == 4, "Should find all 4 test items"

        # Verify items have tags with correct structure
        for item in test_items:
            assert hasattr(item.data, "tags")
            for tag in item.data.tags:
                # Verify tag structure matches ZoteroTag model
                assert hasattr(tag, "tag")
                assert hasattr(tag, "type")
                assert isinstance(tag.type, int)
                assert tag.type in (0, 1), "Tag type must be 0 or 1"

        # Verify tags property returns list of strings
        for item in test_items:
            tags = item.tags
            assert isinstance(tags, list)
            assert all(isinstance(tag, str) for tag in tags)

    @pytest.mark.asyncio
    async def test_search_by_single_tag_via_mcp(
        self,
        collection_key_items_with_tags: list[ZoteroItem],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test filtering items by single tag through search_articles endpoint."""

        # Item 0 has "manual-tag-1"
        search_tag = "manual-tag-1"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_articles", arguments={"tags": [search_tag]}
            )
            response = result.data

        # Should find at least the item with this tag
        assert response.count > 0
        found_items = response.items

        # All returned items must have the searched tag
        for item in found_items:
            assert search_tag in item.tags, f"Item {item.key} should have tag '{search_tag}'"

    @pytest.mark.asyncio
    async def test_search_by_multiple_tags_via_mcp(
        self,
        collection_key_items_with_tags: list[ZoteroItem],
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test AND logic when filtering by multiple tags."""

        # Item 2 has both "manual-mixed" and "auto-mixed"
        search_tags = ["manual-mixed", "auto-mixed"]

        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_articles", arguments={"tags": search_tags}
            )
            response = result.data

        # Should find at least one item with both tags
        assert response.count > 0

        # All returned items must have ALL searched tags (AND logic)
        for item in response.items:
            for tag in search_tags:
                assert tag in item.tags, f"Item {item.key} should have ALL tags: {search_tags}"

    @pytest.mark.asyncio
    async def test_create_note_with_tags_via_mcp(
        self,
        collection_key_items_with_tags: str,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test creating note with tags through create_note_for_item endpoint."""

        note_tags = ["test-note-tag", "automated"]

        async with Client(mcp) as client:
            # Get first item from collection
            items_result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": collection_key_items_with_tags},
            )
            item_key = items_result.data.items[0].key

            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": item_key,
                    "title": "Test Note with Tags",
                    "content": "This note has tags",
                    "tags": note_tags,
                },
            )
            note = result.data

        # Verify note was created with tags
        assert note is not None
        assert note.key
        assert note.tags == note_tags

    @pytest.mark.asyncio
    async def test_item_tags_property_consistency(
        self,
        collection_key_items_with_tags: str,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that tags property consistently returns string list."""

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items", arguments={"collection_key": collection_key_items_with_tags}
            )
            response = result.data

        for item in response.items:
            # Verify tags property returns strings
            tags = item.tags
            assert isinstance(tags, list)

            # Verify length matches data.tags
            assert len(tags) == len(item.data.tags)

            # Verify all are strings
            for tag in tags:
                assert isinstance(tag, str)

            # Verify content matches
            expected_tags = [t.tag for t in item.data.tags]
            assert tags == expected_tags
