"""E2E tests for collection management endpoints."""

import pytest
from fastmcp import Client

from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient


class TestCollectionEndpoints:
    """End-to-end tests for collection management MCP endpoints."""

    @pytest.mark.asyncio
    async def test_create_top_level_collection(
        self,
        test_data_manager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test creating a top-level collection."""

        collection_name = "Test ML Papers"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_collection",
                arguments={"name": collection_name},
            )
            collection_data = result.data

        # Verify collection was created
        assert collection_data is not None
        assert collection_data["key"]
        assert collection_data["name"] == collection_name
        assert collection_data["version"] > 0
        assert collection_data["parent_collection"] is None

        # Clean up: delete the created collection
        await test_zotero_client.delete_collection_by_key(collection_data["key"])

    @pytest.mark.asyncio
    async def test_create_nested_subcollection(
        self,
        test_data_manager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test creating a nested subcollection."""

        # Create parent collection first
        parent_name = "AI Research"
        async with Client(mcp) as client:
            parent_result = await client.call_tool(
                "create_collection",
                arguments={"name": parent_name},
            )
            parent_data = parent_result.data

        # Create subcollection
        child_name = "Neural Networks"
        async with Client(mcp) as client:
            child_result = await client.call_tool(
                "create_collection",
                arguments={
                    "name": child_name,
                    "parent_collection_key": parent_data["key"],
                },
            )
            child_data = child_result.data

        # Verify subcollection was created
        assert child_data is not None
        assert child_data["key"]
        assert child_data["name"] == child_name
        assert child_data["parent_collection"] == parent_data["key"]

        # Clean up: delete both collections (child first)
        await test_zotero_client.delete_collection_by_key(child_data["key"])
        await test_zotero_client.delete_collection_by_key(parent_data["key"])

    @pytest.mark.asyncio
    async def test_create_collection_with_special_chars(
        self,
        test_data_manager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test creating a collection with special characters in name."""

        collection_name = "Deep Learning & NLP (2024)"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_collection",
                arguments={"name": collection_name},
            )
            collection_data = result.data

        # Verify collection was created with correct name
        assert collection_data is not None
        assert collection_data["name"] == collection_name

        # Clean up
        await test_zotero_client.delete_collection_by_key(collection_data["key"])
