"""Tests for note verification (extract_quotes, normalize_text, NoteVerifier)."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from yazot.models import Note
from yazot.verifier import NoteVerifier, extract_quotes, normalize_text


class TestExtractQuotes:
    """Unit tests for blockquote extraction from markdown."""

    def test_single_quote(self) -> None:
        text = "Some text\n> This is a quote\nMore text"
        assert extract_quotes(text) == ["This is a quote"]

    def test_multiple_quotes(self) -> None:
        text = "Intro\n> First quote\nMiddle\n> Second quote\nEnd"
        assert extract_quotes(text) == ["First quote", "Second quote"]

    def test_multiline_quote(self) -> None:
        text = "Intro\n> Line one\n> Line two\n> Line three\nEnd"
        assert extract_quotes(text) == ["Line one Line two Line three"]

    def test_no_quotes(self) -> None:
        text = "Just regular text\nNo quotes here"
        assert extract_quotes(text) == []

    def test_empty_string(self) -> None:
        assert extract_quotes("") == []

    def test_quote_without_space_after_marker(self) -> None:
        text = ">No space after marker"
        assert extract_quotes(text) == ["No space after marker"]

    def test_quote_at_end_of_text(self) -> None:
        text = "Intro\n> Trailing quote"
        assert extract_quotes(text) == ["Trailing quote"]

    def test_mixed_single_and_multiline(self) -> None:
        text = "# Analysis\n> Single quote\n\nSome text\n> Multi line\n> continues here\nEnd"
        assert extract_quotes(text) == ["Single quote", "Multi line continues here"]

    def test_empty_quote_line_filtered(self) -> None:
        text = ">\n"
        assert extract_quotes(text) == []

    def test_nested_blockquote(self) -> None:
        text = ">> Nested quote"
        assert extract_quotes(text) == ["Nested quote"]

    def test_indented_quote(self) -> None:
        text = "  > Indented quote"
        assert extract_quotes(text) == ["Indented quote"]


class TestNormalizeText:
    """Unit tests for text normalization."""

    def test_lowercase(self) -> None:
        assert normalize_text("Hello World") == "hello world"

    def test_collapse_whitespace(self) -> None:
        assert normalize_text("hello   world") == "hello world"

    def test_collapse_newlines(self) -> None:
        assert normalize_text("hello\n\nworld") == "hello world"

    def test_strip(self) -> None:
        assert normalize_text("  hello  ") == "hello"

    def test_tabs_and_mixed_whitespace(self) -> None:
        assert normalize_text("hello\t\n  world") == "hello world"

    def test_empty(self) -> None:
        assert normalize_text("") == ""


class TestNoteVerifier:
    """Integration tests for NoteVerifier with mocked dependencies."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.get_fulltext = AsyncMock(return_value=None)
        client.get_pdf_text = AsyncMock(return_value=None)
        client.get_raw_item = AsyncMock(return_value={"data": {"tags": []}})
        client.update_item = AsyncMock()
        return client

    @pytest.fixture
    def mock_note_manager(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def verifier(self, mock_note_manager: AsyncMock, mock_client: AsyncMock) -> NoteVerifier:
        return NoteVerifier(mock_note_manager, mock_client)

    def _make_note(
        self, content: str, parent_key: str | None = "PARENT01", key: str = "NOTE0001"
    ) -> Note:
        return Note(
            key=key,
            parent_key=parent_key,
            content=content,
            created=datetime.now(),
            modified=datetime.now(),
            tags=[],
        )

    @pytest.mark.asyncio
    async def test_all_quotes_verified(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        note = self._make_note("Analysis\n> the results show significance\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = (
            "In this study, the results show significance in all experiments."
        )

        result = await verifier.verify("NOTE0001")

        assert result.verified is True
        assert result.total_quotes == 1
        assert result.verified_quotes == 1
        assert result.failed_quotes == []
        assert result.tag_added == "verified"
        mock_client.update_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_quote_not_found(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        note = self._make_note("Analysis\n> this text does not exist\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = "Completely different article text."

        result = await verifier.verify("NOTE0001")

        assert result.verified is False
        assert result.total_quotes == 1
        assert result.verified_quotes == 0
        assert result.failed_quotes == ["this text does not exist"]
        assert result.tag_added == "unverified"

    @pytest.mark.asyncio
    async def test_no_quotes_in_note(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        note = self._make_note("Just a plain note without any quotes")
        mock_note_manager.get_note.return_value = note

        result = await verifier.verify("NOTE0001")

        assert result.verified is False
        assert result.total_quotes == 0
        assert result.tag_added == "unverified"

    @pytest.mark.asyncio
    async def test_no_fulltext_available(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        note = self._make_note("Analysis\n> some quote\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = None

        result = await verifier.verify("NOTE0001")

        assert result.verified is False
        assert result.tag_added == "unverified"
        assert result.failed_quotes == ["some quote"]

    @pytest.mark.asyncio
    async def test_fulltext_fallback_to_pdf(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        """When indexed fulltext is unavailable, falls back to PDF text."""
        note = self._make_note("Analysis\n> found in pdf\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = None
        mock_client.get_pdf_text.return_value = "This text was found in pdf extraction."

        result = await verifier.verify("NOTE0001")

        assert result.verified is True
        assert result.tag_added == "verified"

    @pytest.mark.asyncio
    async def test_normalized_comparison(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        """Quotes with different whitespace/case should still match."""
        note = self._make_note("Analysis\n> The  Results   Show\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = "the results\nshow that..."

        result = await verifier.verify("NOTE0001")

        assert result.verified is True

    @pytest.mark.asyncio
    async def test_partial_verification(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        """When some quotes match and some don't — unverified."""
        note = self._make_note("Notes\n> this exists in text\nAlso\n> this does not exist\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = "The article says this exists in text."

        result = await verifier.verify("NOTE0001")

        assert result.verified is False
        assert result.total_quotes == 2
        assert result.verified_quotes == 1
        assert result.failed_quotes == ["this does not exist"]
        assert result.tag_added == "unverified"

    @pytest.mark.asyncio
    async def test_no_parent_key(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        note = self._make_note("Analysis\n> some quote\nEnd", parent_key=None)
        mock_note_manager.get_note.return_value = note

        result = await verifier.verify("NOTE0001")

        assert result.verified is False
        assert result.tag_added == "unverified"

    @pytest.mark.asyncio
    async def test_replaces_opposite_tag(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        """If note already has 'unverified', it should be replaced with 'verified'."""
        note = self._make_note("Analysis\n> exact quote\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = "The exact quote is here."
        mock_client.get_raw_item.return_value = {
            "data": {"tags": [{"tag": "unverified", "type": 1}]}
        }

        await verifier.verify("NOTE0001")

        # Check that update_item was called with tags not containing 'unverified'
        call_args = mock_client.update_item.call_args
        update = call_args[0][1]
        tag_names = [t.tag for t in update.tags]
        assert "verified" in tag_names
        assert "unverified" not in tag_names

    @pytest.mark.asyncio
    async def test_preserves_existing_tags(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        """Existing tags should be preserved when adding verified/unverified."""
        note = self._make_note("Analysis\n> exact quote\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = "The exact quote is here."
        mock_client.get_raw_item.return_value = {
            "data": {"tags": [{"tag": "important", "type": 0}, {"tag": "review", "type": 1}]}
        }

        await verifier.verify("NOTE0001")

        call_args = mock_client.update_item.call_args
        update = call_args[0][1]
        tag_names = [t.tag for t in update.tags]
        assert "important" in tag_names
        assert "review" in tag_names
        assert "verified" in tag_names

    @pytest.mark.asyncio
    async def test_idempotent_when_tag_already_present(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        """If tag already present and no opposite tag, no update_item call."""
        note = self._make_note("Analysis\n> exact quote\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = "The exact quote is here."
        mock_client.get_raw_item.return_value = {"data": {"tags": [{"tag": "verified", "type": 1}]}}

        result = await verifier.verify("NOTE0001")

        assert result.verified is True
        mock_client.update_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_removes_opposite_even_when_tag_present(
        self,
        verifier: NoteVerifier,
        mock_note_manager: AsyncMock,
        mock_client: AsyncMock,
    ) -> None:
        """If both tags present (anomalous state), removes opposite."""
        note = self._make_note("Analysis\n> exact quote\nEnd")
        mock_note_manager.get_note.return_value = note
        mock_client.get_fulltext.return_value = "The exact quote is here."
        mock_client.get_raw_item.return_value = {
            "data": {
                "tags": [
                    {"tag": "verified", "type": 1},
                    {"tag": "unverified", "type": 1},
                ]
            }
        }

        await verifier.verify("NOTE0001")

        call_args = mock_client.update_item.call_args
        update = call_args[0][1]
        tag_names = [t.tag for t in update.tags]
        assert "verified" in tag_names
        assert "unverified" not in tag_names
