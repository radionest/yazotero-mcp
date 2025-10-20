import html
from datetime import datetime

from .models import Note
from .zotero_client import ZoteroClient


class NoteManager:
    """Simple note management for annotations."""

    def __init__(self, client: ZoteroClient):
        self.client = client

    async def create_note(self, item_key: str, content: str, tags: list[str] | None = None) -> Note:
        """Create a new note for an item."""
        note_data = {
            "itemType": "note",
            "parentItem": item_key,
            "note": self._format_note_html(content),
            "tags": [{"tag": tag} for tag in (tags or [])],
        }

        created_note = self.client.client.create_items([note_data])[0]

        return Note(
            key=created_note["key"],
            parent_key=item_key,
            content=content,
            created=datetime.now(),
            modified=datetime.now(),
            tags=tags or [],
        )

    async def get_notes_for_item(self, item_key: str) -> list[Note]:
        """Get all notes for a specific item."""
        children = self.client.client.children(item_key)

        notes = []
        for child in children:
            if child["data"]["itemType"] == "note":
                notes.append(
                    Note(
                        key=child["key"],
                        parent_key=item_key,
                        content=self._extract_note_text(child["data"]["note"]),
                        created=self._parse_datetime(child["data"].get("dateAdded", "")),
                        modified=self._parse_datetime(child["data"].get("dateModified", "")),
                        tags=[tag["tag"] for tag in child["data"].get("tags", [])],
                    )
                )

        return notes

    async def get_note(self, note_key: str) -> Note:
        """Get single note by key."""
        note = self.client.client.item(note_key)
        return Note(
            key=note["key"],
            parent_key=note["data"].get("parentItem"),
            content=self._extract_note_text(note["data"]["note"]),
            created=self._parse_datetime(note["data"].get("dateAdded", "")),
            modified=self._parse_datetime(note["data"].get("dateModified", "")),
            tags=[tag["tag"] for tag in note["data"].get("tags", [])],
        )

    async def update_note(self, note_key: str, content: str) -> Note:
        """Update existing note content."""
        note = self.client.client.item(note_key)
        note["data"]["note"] = self._format_note_html(content)

        self.client.client.update_item(note)

        return Note(
            key=note_key,
            parent_key=note["data"].get("parentItem"),
            content=content,
            created=self._parse_datetime(note["data"].get("dateAdded", "")),
            modified=datetime.now(),
            tags=[tag["tag"] for tag in note["data"].get("tags", [])],
        )

    async def search_notes(self, query: str) -> list[Note]:
        """Search through all notes."""
        # Simple search implementation
        all_items = self.client.client.items()
        notes = []

        query_lower = query.lower()

        for item in all_items:
            if item["data"]["itemType"] == "note":
                note_text = self._extract_note_text(item["data"].get("note", ""))

                if query_lower in note_text.lower():
                    notes.append(
                        Note(
                            key=item["key"],
                            parent_key=item["data"].get("parentItem"),
                            content=note_text[:500],  # First 500 chars
                            created=self._parse_datetime(item["data"].get("dateAdded", "")),
                            modified=self._parse_datetime(item["data"].get("dateModified", "")),
                            tags=[tag["tag"] for tag in item["data"].get("tags", [])],
                        )
                    )

        return notes

    def _format_note_html(self, text: str) -> str:
        """Format plain text as HTML note."""
        # Escape HTML and convert newlines
        text = html.escape(text)
        text = text.replace("\n\n", "</p><p>")
        text = text.replace("\n", "<br>")
        return f"<p>{text}</p>"

    def _extract_note_text(self, html_content: str) -> str:
        """Extract plain text from HTML note."""
        # Simple HTML stripping
        import re

        text = re.sub("<[^<]+?>", "", html_content)
        return html.unescape(text).strip()

    def _parse_datetime(self, date_str: str) -> datetime:
        """Parse datetime string from Zotero."""
        if not date_str:
            return datetime.now()

        try:
            # Try ISO format first
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            # Fallback to current time if parsing fails
            return datetime.now()
