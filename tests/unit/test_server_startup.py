"""Tests for MCP server startup and Zotero connection."""

from unittest.mock import MagicMock, patch

import pytest
from pyzotero import zotero

from yazot.config import Settings
from yazot.exceptions import ConfigurationError
from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient


class TestMCPServerStartup:
    """Test FastMCP server initialization and registration."""

    def test_mcp_server_initialization(self) -> None:
        """Test that MCP server is properly initialized."""
        assert mcp is not None
        assert mcp.name == "zotero-mcp"

    async def test_mcp_tools_registered(self) -> None:
        """Test that all required tools are registered."""
        tool_names = [t.name for t in await mcp.list_tools()]

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
        resource_uris = [str(r.uri) for r in await mcp.list_resources()]

        expected_resources = [
            "resource://collections",
        ]

        for expected_resource in expected_resources:
            assert (
                expected_resource in resource_uris
            ), f"Resource {expected_resource} not registered"

    async def test_mcp_server_metadata(self) -> None:
        """Test that server has correct metadata."""
        assert mcp.name == "zotero-mcp"
        tools = await mcp.list_tools()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"


class TestZoteroConnectionLocal:
    """Test Zotero client connection in local mode."""

    def test_local_client_creation(self, local_zotero_client: ZoteroClient) -> None:
        """Test that local client is created when ZOTERO_LOCAL=true."""
        assert local_zotero_client.mode == "local"
        assert isinstance(local_zotero_client._client, zotero.Zotero)
        assert local_zotero_client._client.local is True

    def test_local_client_operations(self, local_zotero_client: ZoteroClient) -> None:
        """Test that local client has pyzotero methods."""
        local_client = local_zotero_client._client

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
        with patch("yazot.zotero_client.zotero.Zotero") as mock_zotero:
            mock_zotero.return_value = MagicMock()

            client = ZoteroClient(web_settings)

            assert client.mode == "web"
            mock_zotero.assert_called_once_with("123456", "user", "test_api_key_123", local=False)

    def test_web_client_missing_library_id(self) -> None:
        """Test that ZoteroClient raises error when library_id is missing."""
        mock_settings = MagicMock()
        mock_settings.zotero_local = False
        mock_settings.zotero_library_id = ""
        mock_settings.zotero_api_key = "test_key"
        mock_settings.zotero_library_type = "user"

        with pytest.raises(
            ConfigurationError, match="ZOTERO_LIBRARY_ID and ZOTERO_API_KEY required"
        ):
            ZoteroClient(mock_settings)

    def test_web_client_missing_api_key(self) -> None:
        """Test that ZoteroClient raises error when api_key is missing."""
        mock_settings = MagicMock()
        mock_settings.zotero_local = False
        mock_settings.zotero_library_id = "123456"
        mock_settings.zotero_api_key = None
        mock_settings.zotero_library_type = "user"

        with pytest.raises(
            ConfigurationError, match="ZOTERO_LIBRARY_ID and ZOTERO_API_KEY required"
        ):
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

            with patch("yazot.zotero_client.zotero.Zotero") as mock_zotero:
                mock_zotero.return_value = MagicMock()

                client = ZoteroClient(settings)

                mock_zotero.assert_called_once_with("123456", library_type, "test_key", local=False)


class TestClientCaching:
    """Test client singleton and caching behavior."""

    def test_client_cache_operations(self, local_zotero_client: ZoteroClient) -> None:
        """Test that client cache can store and retrieve values."""
        test_key = "test:key"
        test_value = {"data": "test"}

        assert test_key not in local_zotero_client.cache

        local_zotero_client.cache[test_key] = test_value

        assert local_zotero_client.cache[test_key] == test_value

        local_zotero_client.cache.clear()
        assert len(local_zotero_client.cache) == 0
