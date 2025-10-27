"""Tests for MCP resource endpoints."""

import pytest
from fastmcp import Client

import src.zotero_client
from src.mcp_server import mcp
from src.zotero_client import ZoteroClient
from tests.test_helpers import ZoteroTestDataManager


class TestCollectionsResource:
    """Tests for resource://collections endpoint."""

    @pytest.mark.asyncio
    async def test_list_collections_basic(
        self,
        test_data_manager: ZoteroTestDataManager,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that list_collections returns created collections."""
        src.zotero_client.zotero_client = real_zotero_client

        # Create test collections
        collection_keys = await test_data_manager.create_test_collections(
            3, name_prefix="Test Collection"
        )

        # Read resource
        async with Client(mcp) as client:
            result = await client.read_resource("resource://collections")
            content = result[0].text

        # Verify all collections are listed
        for key in collection_keys:
            assert key in content, f"Collection key {key} not found in output"

        # Verify format contains "Test Collection" names
        assert "Test Collection" in content
        assert "key:" in content

    @pytest.mark.asyncio
    async def test_list_collections_empty(
        self,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test list_collections when no collections exist."""
        src.zotero_client.zotero_client = real_zotero_client

        # Clear collections cache to ensure fresh read
        real_zotero_client._collections = None

        async with Client(mcp) as client:
            result = await client.read_resource("resource://collections")
            content = result[0].text

        # Should handle empty case gracefully
        # Either shows "No collections" or lists existing ones
        assert isinstance(content, str)
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_list_collections_format(
        self,
        test_data_manager: ZoteroTestDataManager,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that collection output format is correct."""
        src.zotero_client.zotero_client = real_zotero_client

        # Create one collection with known name
        collection_keys = await test_data_manager.create_test_collections(
            1, name_prefix="Format Test Collection"
        )
        collection_key = collection_keys[0]

        async with Client(mcp) as client:
            result = await client.read_resource("resource://collections")
            content = result[0].text

        # Verify format: "- Name (key: KEY)"
        assert "Format Test Collection" in content
        assert f"key: {collection_key}" in content
        assert "Available Collections:" in content

    @pytest.mark.asyncio
    async def test_list_collections_multiple(
        self,
        test_data_manager: ZoteroTestDataManager,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test listing multiple collections."""
        src.zotero_client.zotero_client = real_zotero_client

        # Create multiple collections with different names
        names = ["Alpha Collection", "Beta Collection", "Gamma Collection"]
        created_keys = []

        for name in names:
            keys = await test_data_manager.create_test_collections(1, name_prefix=name)
            created_keys.extend(keys)

        async with Client(mcp) as client:
            result = await client.read_resource("resource://collections")
            content = result[0].text

        # Verify all collections are present
        for name in names:
            assert name in content

        for key in created_keys:
            assert key in content
