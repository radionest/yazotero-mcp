"""Verification of quotes in notes against article fulltext."""

import re
from typing import TYPE_CHECKING

from .models import ItemUpdate, VerificationResult, ZoteroTag
from .note_manager import NoteManager

if TYPE_CHECKING:
    from .protocols import ZoteroClientProtocol


def extract_quotes(text: str) -> list[str]:
    """Extract blockquote lines from markdown text.

    Collects consecutive `> ` lines into single quotes.
    """
    quotes: list[str] = []
    current_quote_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            # Remove one or more '>' prefixes and optional space
            content = re.sub(r"^>+\s?", "", stripped)
            current_quote_lines.append(content)
        else:
            if current_quote_lines:
                quotes.append(" ".join(current_quote_lines))
                current_quote_lines = []

    if current_quote_lines:
        quotes.append(" ".join(current_quote_lines))

    # Filter out empty quotes
    return [q for q in quotes if q.strip()]


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


class NoteVerifier:
    """Verifies that quotes in notes exist in the article fulltext."""

    def __init__(self, note_manager: NoteManager, client: "ZoteroClientProtocol"):
        self.note_manager = note_manager
        self.client = client

    async def _get_fulltext(self, item_key: str) -> str | None:
        """Get fulltext for item, trying indexed API then PDF fallback."""
        text = await self.client.get_fulltext(item_key)
        if text:
            return text
        return await self.client.get_pdf_text(item_key)

    async def _add_tag_to_note(self, note_key: str, tag: str) -> None:
        """Add a tag to a note, preserving existing tags."""
        raw_note = await self.client.get_raw_item(note_key)
        existing_tags = raw_note["data"].get("tags", [])

        # Remove opposite tag if present
        opposite = "unverified" if tag == "verified" else "verified"
        new_tags = [t for t in existing_tags if t["tag"] != opposite]

        # Don't duplicate tags
        if any(t["tag"] == tag for t in new_tags):
            if len(new_tags) == len(existing_tags):
                return  # No changes needed
        else:
            new_tags.append({"tag": tag, "type": 1})

        await self.client.update_item(
            note_key,
            ItemUpdate(tags=[ZoteroTag(tag=t["tag"], type=t.get("type", 0)) for t in new_tags]),
        )

    async def verify(self, note_key: str) -> VerificationResult:
        """Verify all quotes in a note against the parent article's fulltext."""
        note = await self.note_manager.get_note(note_key)

        quotes = extract_quotes(note.content)

        if not quotes:
            await self._add_tag_to_note(note_key, "unverified")
            return VerificationResult(
                note_key=note_key,
                verified=False,
                total_quotes=0,
                verified_quotes=0,
                tag_added="unverified",
            )

        # Get parent item fulltext
        parent_key = note.parent_key
        if not parent_key:
            await self._add_tag_to_note(note_key, "unverified")
            return VerificationResult(
                note_key=note_key,
                verified=False,
                total_quotes=len(quotes),
                verified_quotes=0,
                failed_quotes=quotes,
                tag_added="unverified",
            )

        fulltext = await self._get_fulltext(parent_key)

        if not fulltext:
            await self._add_tag_to_note(note_key, "unverified")
            return VerificationResult(
                note_key=note_key,
                verified=False,
                total_quotes=len(quotes),
                verified_quotes=0,
                failed_quotes=quotes,
                tag_added="unverified",
            )

        normalized_fulltext = normalize_text(fulltext)

        verified_count = 0
        failed: list[str] = []

        for quote in quotes:
            if normalize_text(quote) in normalized_fulltext:
                verified_count += 1
            else:
                failed.append(quote)

        is_verified = verified_count == len(quotes)
        tag = "verified" if is_verified else "unverified"

        await self._add_tag_to_note(note_key, tag)

        return VerificationResult(
            note_key=note_key,
            verified=is_verified,
            total_quotes=len(quotes),
            verified_quotes=verified_count,
            failed_quotes=failed,
            tag_added=tag,
        )
