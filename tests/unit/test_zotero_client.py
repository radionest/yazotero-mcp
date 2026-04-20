"""Tests for ZoteroClient: add_to_collection retry, fulltext truncation detection."""

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


def _make_zotero_client(*, mode: str = "web") -> Any:
    """Create a ZoteroClient with mocked internals for unit testing."""
    with patch("yazot.zotero_client.ZoteroClient.__init__", return_value=None):
        from yazot.zotero_client import ZoteroClient

        zc = ZoteroClient.__new__(ZoteroClient)
        zc._mode = mode
        zc._client = MagicMock()  # pyzotero client stub
        zc._call = AsyncMock(return_value=None)
        zc._cache = {}
        zc._semaphore = None
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


class TestFulltextTruncationDetection:
    """Test that truncated indexed fulltext falls back to PDF parsing."""

    @pytest.mark.asyncio
    async def test_get_item_fulltext_falls_back_on_truncation(self) -> None:
        """When indexedChars < totalChars, get_item_fulltext should skip indexed and use PDF."""
        zc = _make_zotero_client()
        zc._find_pdf_attachment_key = AsyncMock(return_value="PDFKEY01")

        truncated_indexed = "First part of text..."
        full_pdf_text = "First part of text... and much more content from PDF."

        # fulltext_item returns truncated indexed content
        zc._client.fulltext_item = MagicMock(
            return_value={
                "content": truncated_indexed,
                "indexedChars": 20,
                "totalChars": 50,
            }
        )
        # PDF file download returns complete content
        zc._client.file = MagicMock(return_value=b"fake pdf bytes")

        with patch("yazot.zotero_client.extract_text_from_pdf", return_value=full_pdf_text):
            result = await zc.get_item_fulltext("ITEM0001")

        assert result == full_pdf_text

    @pytest.mark.asyncio
    async def test_get_item_fulltext_uses_indexed_when_not_truncated(self) -> None:
        """When indexedChars == totalChars, get_item_fulltext returns indexed text."""
        zc = _make_zotero_client()
        zc._find_pdf_attachment_key = AsyncMock(return_value="PDFKEY01")

        indexed_text = "Complete indexed text."
        zc._client.fulltext_item = MagicMock(
            return_value={
                "content": indexed_text,
                "indexedChars": 22,
                "totalChars": 22,
            }
        )

        result = await zc.get_item_fulltext("ITEM0001")

        assert result == indexed_text
        zc._client.file.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_item_fulltext_uses_indexed_when_no_char_counts(self) -> None:
        """When indexedChars/totalChars not in response, use indexed text as-is."""
        zc = _make_zotero_client()
        zc._find_pdf_attachment_key = AsyncMock(return_value="PDFKEY01")

        indexed_text = "Text without char counts."
        zc._client.fulltext_item = MagicMock(return_value={"content": indexed_text})

        result = await zc.get_item_fulltext("ITEM0001")

        assert result == indexed_text
        zc._client.file.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_fulltext_returns_none_on_truncation(self) -> None:
        """get_fulltext (indexed-only) should return None when text is truncated."""
        zc = _make_zotero_client()
        zc._find_pdf_attachment_key = AsyncMock(return_value="PDFKEY01")
        zc._call = AsyncMock(
            return_value={
                "content": "Truncated text.",
                "indexedChars": 15,
                "totalChars": 100,
            }
        )

        result = await zc.get_fulltext("ITEM0001")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_fulltext_returns_text_when_not_truncated(self) -> None:
        """get_fulltext returns indexed text when not truncated."""
        zc = _make_zotero_client()
        zc._find_pdf_attachment_key = AsyncMock(return_value="PDFKEY01")
        zc._call = AsyncMock(
            return_value={
                "content": "Complete text.",
                "indexedChars": 14,
                "totalChars": 14,
            }
        )

        result = await zc.get_fulltext("ITEM0001")

        assert result == "Complete text."
