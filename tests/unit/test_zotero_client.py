"""Tests for ZoteroClient.add_to_collection retry logic."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pyzotero import zotero_errors

from yazot.exceptions import ZoteroError
from yazot.models import ZoteroItem


def _make_item(key: str = "TESTKEY1", version: int = 100) -> ZoteroItem:
    """Create a minimal ZoteroItem for testing."""
    return ZoteroItem.model_validate(
        {
            "key": key,
            "version": version,
            "data": {
                "key": key,
                "version": version,
                "itemType": "journalArticle",
                "title": "Test Article",
                "collections": [],
            },
            "meta": {},
        }
    )


def _make_zotero_client() -> Any:
    """Create a ZoteroClient with mocked internals for unit testing."""
    with patch("yazot.zotero_client.ZoteroClient.__init__", return_value=None):
        from yazot.zotero_client import ZoteroClient

        zc = ZoteroClient.__new__(ZoteroClient)
        zc._mode = "web"
        zc._client = MagicMock()  # pyzotero client stub
        zc._call = AsyncMock(return_value=None)
        return zc


class TestAddToCollectionRetry:
    """Test 412 PreConditionFailed retry in add_to_collection."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self) -> None:
        """Normal add without version conflict — no retry needed."""
        zc = _make_zotero_client()
        item = _make_item()

        await zc._add_item_to_collection("COLL1", item)

        zc._call.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_412(self) -> None:
        """412 triggers re-fetch and single retry."""
        zc = _make_zotero_client()
        fresh_item = _make_item(version=200)

        zc._call = AsyncMock(side_effect=[zotero_errors.PreConditionFailedError("412"), None])
        zc.get_item = AsyncMock(return_value=fresh_item)

        item = _make_item(version=100)
        await zc._add_item_to_collection("COLL1", item)

        assert zc._call.call_count == 2
        zc.get_item.assert_called_once_with("TESTKEY1")

    @pytest.mark.asyncio
    async def test_412_after_retry_raises(self) -> None:
        """Second 412 after retry raises ZoteroError."""
        zc = _make_zotero_client()
        fresh_item = _make_item(version=200)

        zc._call = AsyncMock(
            side_effect=[
                zotero_errors.PreConditionFailedError("412"),
                zotero_errors.PreConditionFailedError("412 again"),
            ]
        )
        zc.get_item = AsyncMock(return_value=fresh_item)

        item = _make_item(version=100)
        with pytest.raises(ZoteroError, match="Version conflict.*after retry"):
            await zc._add_item_to_collection("COLL1", item)

    @pytest.mark.asyncio
    async def test_non_412_error_not_retried(self) -> None:
        """Non-412 PyZoteroError is not retried."""
        zc = _make_zotero_client()
        zc._call = AsyncMock(side_effect=zotero_errors.PyZoteroError("500 Server Error"))

        item = _make_item()
        with pytest.raises(ZoteroError, match="Failed to add item"):
            await zc._add_item_to_collection("COLL1", item)

        zc._call.assert_called_once()
