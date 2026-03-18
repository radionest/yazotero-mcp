"""Tests for MCP server startup and Zotero connection."""

import os
from unittest.mock import MagicMock, patch

import pytest
from pyzotero import zotero

from src.config import Settings
from src.mcp_server import mcp
from src.zotero_client import ZoteroClient


class TestMCPServerStartup:
    """Test FastMCP server initialization and registration."""

    def test_mcp_server_initialization(self) -> None:
        """Test that MCP server is properly initialized."""
        assert mcp is not None
        assert mcp.name == "zotero-mcp"

    async def test_mcp_tools_registered(self) -> None:
        """Test that all required tools are registered."""
        # Get registered tool names
        tool_names = [tool.name for tool in await mcp._list_tools()]

        # Verify all expected tools are registered
        expected_tools = [
            "get_collection_items",
            "search_articles",
            "create_note_for_item",
            "get_next_chunk",
            "get_item_fulltext",
            "get_next_fulltext_chunk",
        ]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Tool {expected_tool} not registered"

    async def test_mcp_resources_registered(self) -> None:
        """Test that all required resources are registered."""
        # Get registered resource URIs (convert to string for comparison)
        resource_uris = [str(resource.uri) for resource in await mcp._list_resources()]

        # Verify expected resources are registered
        expected_resources = [
            "resource://collections",
            "resource://tags",
        ]

        for expected_resource in expected_resources:
            assert (
                expected_resource in resource_uris
            ), f"Resource {expected_resource} not registered"

    async def test_mcp_server_metadata(self) -> None:
        """Test that server has correct metadata."""
        assert mcp.name == "zotero-mcp"
        # Verify tools have descriptions
        tools = await mcp._list_tools()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"


class TestZoteroConnectionLocal:
    """Test Zotero client connection in local mode."""

    def test_local_client_creation(self, local_zotero_client: ZoteroClient) -> None:
        """Test that local client is created when ZOTERO_LOCAL=true.

        NOTE: This test accesses private _client attribute for internal validation.
        """
        assert local_zotero_client.mode == "local"
        assert isinstance(local_zotero_client._client, zotero.Zotero)
        assert local_zotero_client._client.local is True

    def test_local_client_operations(self, local_zotero_client: ZoteroClient) -> None:
        """Test that local client has pyzotero methods.

        NOTE: This test accesses private _client attribute for internal validation.
        """
        local_client = local_zotero_client._client

        # Verify client has pyzotero methods (don't call them without server running)
        assert hasattr(local_client, "collection_items")
        assert hasattr(local_client, "collections_sub")
        assert hasattr(local_client, "item")
        assert hasattr(local_client, "items")
        assert hasattr(local_client, "children")
        assert hasattr(local_client, "everything")
        assert hasattr(local_client, "makeiter")

    def test_local_client_cache(self, local_zotero_client: ZoteroClient) -> None:
        """Test that local client has cache initialized."""
        assert hasattr(local_zotero_client, "cache")
        assert isinstance(local_zotero_client.cache, dict)
        assert len(local_zotero_client.cache) == 0


class TestZoteroConnectionHTTP:
    """Test Zotero client connection in HTTP/web mode."""

    def test_web_client_creation_success(self, web_settings: Settings) -> None:
        """Test that web client is created with valid credentials."""
        # Mock pyzotero.Zotero to avoid actual API call
        with patch("src.zotero_client.zotero.Zotero") as mock_zotero:
            mock_zotero.return_value = MagicMock()

            client = ZoteroClient(web_settings)

            assert client.mode == "web"
            # Verify Zotero was called with correct params (including local=False)
            mock_zotero.assert_called_once_with("123456", "user", "test_api_key_123", local=False)

    def test_web_client_missing_library_id(self) -> None:
        """Test that ZoteroClient raises error when library_id is missing."""
        # Create a mock settings object that bypasses Pydantic validation
        mock_settings = MagicMock()
        mock_settings.zotero_local = False
        mock_settings.zotero_library_id = ""  # Empty library_id
        mock_settings.zotero_api_key = "test_key"
        mock_settings.zotero_library_type = "user"

        with pytest.raises(ValueError, match="ZOTERO_LIBRARY_ID and ZOTERO_API_KEY required"):
            ZoteroClient(mock_settings)

    def test_web_client_missing_api_key(self) -> None:
        """Test that ZoteroClient raises error when api_key is missing."""
        # Create a mock settings object that bypasses Pydantic validation
        mock_settings = MagicMock()
        mock_settings.zotero_local = False
        mock_settings.zotero_library_id = "123456"
        mock_settings.zotero_api_key = None  # Missing API key
        mock_settings.zotero_library_type = "user"

        with pytest.raises(ValueError, match="ZOTERO_LIBRARY_ID and ZOTERO_API_KEY required"):
            ZoteroClient(mock_settings)

    def test_web_client_cache_initialized(self, web_zotero_client: ZoteroClient) -> None:
        """Test that web client has cache initialized."""
        assert hasattr(web_zotero_client, "cache")
        assert isinstance(web_zotero_client.cache, dict)
        assert len(web_zotero_client.cache) == 0

    def test_web_client_library_types(self) -> None:
        """Test that different library types are supported."""
        for library_type in ["user", "group"]:
            settings = Settings(
                zotero_local=False,
                zotero_library_id="123456",
                zotero_api_key="test_key",
                zotero_library_type=library_type,
            )

            with patch("src.zotero_client.zotero.Zotero") as mock_zotero:
                mock_zotero.return_value = MagicMock()

                client = ZoteroClient(settings)

                # Verify library_type was passed correctly (with local=False)
                mock_zotero.assert_called_once_with("123456", library_type, "test_key", local=False)


class TestClientCaching:
    """Test client singleton and caching behavior."""

    def test_client_cache_operations(self, local_zotero_client: ZoteroClient) -> None:
        """Test that client cache can store and retrieve values."""
        # Test cache operations
        test_key = "test:key"
        test_value = {"data": "test"}

        # Cache should be empty
        assert test_key not in local_zotero_client.cache

        # Add to cache
        local_zotero_client.cache[test_key] = test_value

        # Should be retrievable
        assert local_zotero_client.cache[test_key] == test_value

        # Clear cache
        local_zotero_client.cache.clear()
        assert len(local_zotero_client.cache) == 0


class TestZoteroConnectionIntegration:
    """Integration tests for real Zotero connections (if credentials available)."""

    def test_real_web_connection(self) -> None:
        """Test connection to real Zotero web API (requires credentials)."""
        # Check credentials inside test (after .env.test is loaded by conftest)
        if not os.getenv("TEST_ZOTERO_LIBRARY_ID") or not os.getenv("TEST_ZOTERO_API_KEY"):
            pytest.skip("Real Zotero credentials not available")

        real_settings = Settings(
            zotero_local=False,
            zotero_library_id=os.getenv("TEST_ZOTERO_LIBRARY_ID", ""),
            zotero_api_key=os.getenv("TEST_ZOTERO_API_KEY"),
            zotero_library_type=os.getenv("TEST_ZOTERO_LIBRARY_TYPE", "user"),
        )

        # Create client - should not raise
        client = ZoteroClient(real_settings)

        assert client.mode == "web"
        # NOTE: Internal test - checking _client implementation
        assert isinstance(client._client, zotero.Zotero)

        # Try a simple API call to verify connection
        try:
            # This will make a real API call
            # NOTE: Internal test - using _client directly for connection test
            items = client._client.items(limit=1)
            assert isinstance(items, list)
        except Exception as e:
            pytest.fail(f"Failed to connect to real Zotero API: {e}")

    def test_real_local_connection(self) -> None:
        """Test connection to local Zotero server (if available)."""
        # Check configuration inside test (after .env.test is loaded by conftest)
        if os.getenv("TEST_ZOTERO_LOCAL", "false").lower() != "true":
            pytest.skip("Local Zotero not configured")

        local_settings = Settings(
            zotero_local=True,
            zotero_library_id="",
            zotero_api_key=None,
        )

        # Create client - should not raise
        client = ZoteroClient(local_settings)

        assert client.mode == "local"
        # NOTE: Internal test - checking _client implementation
        assert isinstance(client._client, zotero.Zotero)
        assert client._client.local is True
        # Verify endpoint is set to localhost
        assert client._client.endpoint == "http://localhost:23119/api"
