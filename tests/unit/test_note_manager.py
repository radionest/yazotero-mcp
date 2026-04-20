"""Unit tests for NoteManager.update_note()."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from yazot.exceptions import ZoteroNotFoundError
from yazot.note_manager import NoteManager


def _make_raw_note(
    key: str = "NOTE0001",
    parent_key: str = "PARENT01",
    note_html: str = "<p>old content</p>",
    tags: list[dict] | None = None,
) -> dict:
    return {
        "key": key,
        "data": {
            "parentItem": parent_key,
            "note": note_html,
            "dateAdded": "2025-01-01T00:00:00Z",
            "dateModified": "2025-01-01T12:00:00Z",
            "tags": tags or [],
        },
    }


class TestUpdateNote:
    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.update_item = AsyncMock()
        client.get_raw_item = AsyncMock(return_value=_make_raw_note())
        return client

    @pytest.fixture
    def note_manager(self, mock_client: AsyncMock) -> NoteManager:
        return NoteManager(mock_client)

    @pytest.mark.asyncio
    async def test_update_note_with_string_content(
        self, note_manager: NoteManager, mock_client: AsyncMock
    ) -> None:
        result = await note_manager.update_note("NOTE0001", "new plain text")

        mock_client.update_item.assert_called_once()
        call_args = mock_client.update_item.call_args
        assert call_args[0][0] == "NOTE0001"
        update = call_args[0][1]
        assert update.note is not None
        assert result.key == "NOTE0001"

    @pytest.mark.asyncio
    async def test_update_note_with_dict_content(
        self, note_manager: NoteManager, mock_client: AsyncMock
    ) -> None:
        content = {"summary": "Test summary", "findings": ["A", "B"]}
        result = await note_manager.update_note("NOTE0001", content)

        mock_client.update_item.assert_called_once()
        assert result.key == "NOTE0001"

    @pytest.mark.asyncio
    async def test_update_note_with_json_string(
        self, note_manager: NoteManager, mock_client: AsyncMock
    ) -> None:
        content = '{"summary": "Test summary"}'
        result = await note_manager.update_note("NOTE0001", content)

        mock_client.update_item.assert_called_once()
        assert result.key == "NOTE0001"

    @pytest.mark.asyncio
    async def test_update_note_preserves_tags(
        self, note_manager: NoteManager, mock_client: AsyncMock
    ) -> None:
        mock_client.get_raw_item.return_value = _make_raw_note(
            tags=[{"tag": "important", "type": 1}, {"tag": "verified", "type": 1}]
        )

        result = await note_manager.update_note("NOTE0001", "updated content")

        # update_item should NOT include tags (content-only update)
        update = mock_client.update_item.call_args[0][1]
        assert update.tags is None
        # Returned note should still have existing tags
        assert result.tags == ["important", "verified"]

    @pytest.mark.asyncio
    async def test_update_note_returns_refreshed_metadata(
        self, note_manager: NoteManager, mock_client: AsyncMock
    ) -> None:
        result = await note_manager.update_note("NOTE0001", "new content")

        assert result.parent_key == "PARENT01"
        assert isinstance(result.created, datetime)
        assert isinstance(result.modified, datetime)

    @pytest.mark.asyncio
    async def test_update_note_not_found(
        self, note_manager: NoteManager, mock_client: AsyncMock
    ) -> None:
        mock_client.update_item.side_effect = ZoteroNotFoundError("item", "BADKEY01")

        with pytest.raises(ZoteroNotFoundError):
            await note_manager.update_note("BADKEY01", "content")
