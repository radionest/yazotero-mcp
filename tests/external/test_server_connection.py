"""Integration tests for real Zotero connections (if credentials available)."""

import os

import pytest
from pyzotero import zotero

from yazot.config import Settings
from yazot.zotero_client import ZoteroClient


class TestZoteroConnectionIntegration:
    """Integration tests for real Zotero connections (if credentials available)."""

    def test_real_web_connection(self) -> None:
        """Test connection to real Zotero web API (requires credentials)."""
        if not os.getenv("TEST_ZOTERO_LIBRARY_ID") or not os.getenv("TEST_ZOTERO_API_KEY"):
            pytest.skip("Real Zotero credentials not available")

        real_settings = Settings(
            zotero_local=False,
            zotero_library_id=os.getenv("TEST_ZOTERO_LIBRARY_ID", ""),
            zotero_api_key=os.getenv("TEST_ZOTERO_API_KEY"),
            zotero_library_type=os.getenv("TEST_ZOTERO_LIBRARY_TYPE", "user"),
        )

        client = ZoteroClient(real_settings)

        assert client.mode == "web"
        assert isinstance(client._client, zotero.Zotero)

        try:
            items = client._client.items(limit=1)
            assert isinstance(items, list)
        except Exception as e:
            pytest.fail(f"Failed to connect to real Zotero API: {e}")

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
