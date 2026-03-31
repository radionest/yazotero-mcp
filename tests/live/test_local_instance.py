"""Tests against live local Zotero instance."""

import os
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client
from pyzotero import zotero

from yazot.config import Settings
from yazot.mcp_server import mcp
from yazot.models import ZoteroSearchParams
from yazot.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.live.zotero_instance import ZoteroInstance


class TestLocalInstanceRead:
    """Tests that exercise ZoteroClient against a live local Zotero process.

    Every test skips when ZOTERO_TEST_INSTANCE is not enabled (fixture yields None).
    """

    def test_instance_health_check(
        self,
        zotero_test_environment: "ZoteroInstance | None",
    ) -> None:
        """Verify the provisioned Zotero process responds to HTTP health checks."""
        if zotero_test_environment is None:
            pytest.skip("Live Zotero instance not enabled")

        assert zotero_test_environment.health_check() is True

    def test_client_connects_with_custom_port(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """ZoteroClient created for the live instance uses local mode and correct port."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        assert local_live_client.mode == "local"
        assert str(zotero_test_environment.port) in local_live_client._client.endpoint

    async def test_get_items_returns_list(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """get_items() against the live local instance returns a list."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        items = await local_live_client.get_items()
        assert isinstance(items, list)

    async def test_get_collections_returns_list(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """get_collections() against the live local instance returns a list."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        collections = await local_live_client.get_collections()
        assert isinstance(collections, list)

    async def test_search_items_returns_list(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """search_items() with empty params against live local instance returns a list."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        items = await local_live_client.search_items(ZoteroSearchParams())
        assert isinstance(items, list)

    async def test_mcp_search_via_local_instance(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MCP search_articles tool works when env vars point to the live local instance."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        port = zotero_test_environment.port
        monkeypatch.setenv("ZOTERO_LOCAL", "true")
        monkeypatch.setenv("ZOTERO_PORT", str(port))
        monkeypatch.setenv("ZOTERO_LIBRARY_ID", "0")
        monkeypatch.setenv("ZOTERO_API_KEY", "")

        async with Client(mcp) as client:
            result = await client.call_tool("search_articles", arguments={})
            response = result.data

        assert isinstance(response.items, list)
        assert response.count >= 0


class TestLocalConnectionSmoke:
    """Smoke test for local Zotero client creation."""

    def test_real_local_connection(self) -> None:
        """Test connection to local Zotero server (if available)."""
        if os.getenv("TEST_ZOTERO_LOCAL", "false").lower() != "true":
            pytest.skip("Local Zotero not configured")

        local_settings = Settings(
            zotero_local=True,
            zotero_library_id="",
            zotero_api_key=None,
        )

        client = ZoteroClient(local_settings)

        assert client.mode == "local"
        assert isinstance(client._client, zotero.Zotero)
        assert client._client.local is True
        assert client._client.endpoint == "http://localhost:23119/api"
