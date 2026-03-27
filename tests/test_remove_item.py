"""Tests for remove_item MCP tool."""

import pytest
from fastmcp import Client

from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient

from .test_helpers import ZoteroTestDataManager


class TestRemoveItemFromCollection:
    """Test smart removal behavior when collection_key is provided."""

    @pytest.mark.asyncio
    async def test_remove_item_single_collection_deletes_from_library(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Item in only one collection should be deleted from library entirely."""
        # Create collection and item
        coll_keys = await test_data_manager.create_test_collections(1, name_prefix="Single Coll")
        items = await test_data_manager.create_test_items(1, coll_keys[0])
        item_key = items[0].key

        async with Client(mcp) as client:
            result = await client.call_tool(
                "remove_item",
                arguments={"item_key": item_key, "collection_key": coll_keys[0]},
            )

        assert result.data["action"] == "deleted_from_library"
        assert result.data["item_key"] == item_key
        assert "reason" in result.data

        # Item should no longer exist — remove from cleanup tracking
        test_data_manager.created_items = [
            i for i in test_data_manager.created_items if i.key != item_key
        ]

    @pytest.mark.asyncio
    async def test_remove_item_multiple_collections_removes_from_collection(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Item in multiple collections should only be removed from specified collection."""
        # Create two collections
        coll_keys = await test_data_manager.create_test_collections(2, name_prefix="Multi Coll")
        # Create item in first collection
        items = await test_data_manager.create_test_items(1, coll_keys[0])
        item_key = items[0].key
        # Add same item to second collection
        await test_data_manager.add_items_to_collection(items, coll_keys[1])

        async with Client(mcp) as client:
            result = await client.call_tool(
                "remove_item",
                arguments={"item_key": item_key, "collection_key": coll_keys[0]},
            )

        assert result.data["action"] == "removed_from_collection"
        assert result.data["item_key"] == item_key
        assert result.data["collection_key"] == coll_keys[0]
        assert result.data["remaining_collections"] >= 1

        # Verify item still exists in library
        item = await test_zotero_client.get_item(item_key)
        assert item is not None
        assert coll_keys[0] not in item.data.collections


class TestRemoveItemFromLibrary:
    """Test forced deletion from library."""

    @pytest.mark.asyncio
    async def test_from_library_deletes_item(
        self,
        test_data_manager: ZoteroTestDataManager,
    ) -> None:
        """from_library=True should delete item from library."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            result = await client.call_tool(
                "remove_item",
                arguments={"item_key": item_key, "from_library": True},
            )

        assert result.data["action"] == "deleted_from_library"
        assert result.data["item_key"] == item_key

        # Remove from cleanup tracking
        test_data_manager.created_items = [
            i for i in test_data_manager.created_items if i.key != item_key
        ]

    @pytest.mark.asyncio
    async def test_from_library_overrides_collection_key(
        self,
        test_data_manager: ZoteroTestDataManager,
    ) -> None:
        """from_library=True with collection_key should still delete from library."""
        coll_keys = await test_data_manager.create_test_collections(2, name_prefix="Override Coll")
        items = await test_data_manager.create_test_items(1, coll_keys[0])
        item_key = items[0].key
        await test_data_manager.add_items_to_collection(items, coll_keys[1])

        async with Client(mcp) as client:
            result = await client.call_tool(
                "remove_item",
                arguments={
                    "item_key": item_key,
                    "collection_key": coll_keys[0],
                    "from_library": True,
                },
            )

        assert result.data["action"] == "deleted_from_library"

        # Remove from cleanup tracking
        test_data_manager.created_items = [
            i for i in test_data_manager.created_items if i.key != item_key
        ]


class TestRemoveItemValidation:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_no_parameters_raises_error(self) -> None:
        """Calling without collection_key or from_library should raise error."""
        async with Client(mcp) as client:
            with pytest.raises(Exception, match=r"collection_key|from_library"):
                await client.call_tool(
                    "remove_item",
                    arguments={"item_key": "NONEXISTENT"},
                )

    @pytest.mark.asyncio
    async def test_item_not_in_collection_raises_error(
        self,
        test_data_manager: ZoteroTestDataManager,
    ) -> None:
        """Item not in specified collection should raise error."""
        items = await test_data_manager.create_test_items(1)
        item_key = items[0].key

        async with Client(mcp) as client:
            with pytest.raises(Exception, match=r"not in collection"):
                await client.call_tool(
                    "remove_item",
                    arguments={"item_key": item_key, "collection_key": "NONEXISTENT"},
                )
