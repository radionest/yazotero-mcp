"""E2E tests for update_item_tags MCP tool."""

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.e2e.conftest import parse_tool_result_dict
from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.e2e.test_helpers import ZoteroTestDataManager


class TestUpdateItemTagsAdd:
    """Tests for mode='add' (default)."""

    @pytest.mark.asyncio
    async def test_add_new_tags(
        self,
        test_data_manager: "ZoteroTestDataManager",
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Adding new tags to an item with no tags."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["new-tag-1", "new-tag-2"]},
            )
        data = parse_tool_result_dict(result)

        assert data["changed"] is True
        assert data["mode"] == "add"
        assert "new-tag-1" in data["tags_after"]
        assert "new-tag-2" in data["tags_after"]

        # Verify via direct API
        updated = await test_zotero_client.get_item(item_key)
        assert "new-tag-1" in updated.tags
        assert "new-tag-2" in updated.tags

    @pytest.mark.asyncio
    async def test_add_duplicate_tags_no_change(
        self,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Adding tags that already exist results in changed=False."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            # First add
            await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["existing"]},
            )
            # Second add — same tag
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["existing"]},
            )
        data = parse_tool_result_dict(result)

        assert data["changed"] is False
        assert data["tags_before"] == data["tags_after"]

    @pytest.mark.asyncio
    async def test_add_preserves_existing_tag_types(
        self,
        collection_key_items_with_tags: str,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Adding new tags preserves type of existing auto-tags (type=0) and creates new with type=1."""
        # Get an item with auto tags (type=0)
        async with Client(mcp) as client:
            from tests.e2e.conftest import parse_tool_result
            from yazot.models import SearchCollectionResponse

            items_result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": collection_key_items_with_tags},
            )
            items = parse_tool_result(items_result, SearchCollectionResponse).items

        # Find item with auto tags
        auto_item = next(
            (i for i in items if any(t.type == 0 for t in i.data.tags)),
            None,
        )
        assert auto_item is not None, "Test fixture should have items with auto-tags"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": auto_item.key, "tags": ["extra-tag"]},
            )
        data = parse_tool_result_dict(result)
        assert data["changed"] is True

        # Verify existing auto-tags preserved their type via raw API
        raw = await test_zotero_client.get_raw_item(auto_item.key)
        raw_tags = raw["data"]["tags"]
        auto_tags = [t for t in raw_tags if t["type"] == 0]
        assert len(auto_tags) > 0, "Auto-tags should be preserved with type=0"

        # Verify newly added tag has type=1
        extra = next((t for t in raw_tags if t["tag"] == "extra-tag"), None)
        assert extra is not None, "Newly added tag should exist"
        assert extra["type"] == 1, "Newly added tag should have type=1"

    @pytest.mark.asyncio
    async def test_add_empty_list_is_noop(
        self,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Adding empty list returns changed=False."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": []},
            )
        data = parse_tool_result_dict(result)

        assert data["changed"] is False

    @pytest.mark.asyncio
    async def test_default_mode_is_add(
        self,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Calling without mode uses 'add'."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["default-mode-tag"]},
            )
        data = parse_tool_result_dict(result)

        assert data["mode"] == "add"
        assert data["changed"] is True


class TestUpdateItemTagsRemove:
    """Tests for mode='remove'."""

    @pytest.mark.asyncio
    async def test_remove_existing_tags(
        self,
        test_data_manager: "ZoteroTestDataManager",
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Removing existing tags removes them."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            # Setup: add tags
            await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["keep-me", "remove-me"]},
            )
            # Remove one tag
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["remove-me"], "mode": "remove"},
            )
        data = parse_tool_result_dict(result)

        assert data["changed"] is True
        assert "remove-me" not in data["tags_after"]
        assert "keep-me" in data["tags_after"]

        # Verify via direct API
        updated = await test_zotero_client.get_item(item_key)
        assert "remove-me" not in updated.tags
        assert "keep-me" in updated.tags

    @pytest.mark.asyncio
    async def test_remove_nonexistent_tags_no_change(
        self,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Removing tags that don't exist returns changed=False."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["nonexistent"], "mode": "remove"},
            )
        data = parse_tool_result_dict(result)

        assert data["changed"] is False


class TestUpdateItemTagsReplace:
    """Tests for mode='replace'."""

    @pytest.mark.asyncio
    async def test_replace_all_tags(
        self,
        test_data_manager: "ZoteroTestDataManager",
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Replace mode sets exactly the specified tags."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            # Setup: add tags
            await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["old-tag-1", "old-tag-2"]},
            )
            # Replace
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["new-tag"], "mode": "replace"},
            )
        data = parse_tool_result_dict(result)

        assert data["changed"] is True
        assert data["tags_after"] == ["new-tag"]

        # Verify via direct API
        updated = await test_zotero_client.get_item(item_key)
        assert updated.tags == ["new-tag"]

    @pytest.mark.asyncio
    async def test_replace_with_empty_clears_tags(
        self,
        test_data_manager: "ZoteroTestDataManager",
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Replace with empty list clears all tags."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            # Setup: add tags
            await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": ["some-tag"]},
            )
            # Clear
            result = await client.call_tool(
                "update_item_tags",
                arguments={"item_key": item_key, "tags": [], "mode": "replace"},
            )
        data = parse_tool_result_dict(result)

        assert data["changed"] is True
        assert data["tags_after"] == []

        # Verify via direct API
        updated = await test_zotero_client.get_item(item_key)
        assert updated.tags == []


class TestUpdateItemTagsErrors:
    """Error handling tests."""

    @pytest.mark.asyncio
    async def test_nonexistent_item_raises_error(self) -> None:
        """Non-existent item_key raises error."""
        async with Client(mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "update_item_tags",
                    arguments={"item_key": "NONEXISTENT999", "tags": ["x"]},
                )
