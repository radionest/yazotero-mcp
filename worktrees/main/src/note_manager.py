import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .formatters import (
    extract_note_text,
    format_dict_to_html,
    format_note_html,
    parse_datetime,
)
from .models import ItemCreate, ItemUpdate, Note, ZoteroTag

if TYPE_CHECKING:
    from .protocols import ZoteroClientProtocol


class NoteManager:
    """Simple note management for annotations."""

    def __init__(self, client: "ZoteroClientProtocol"):
        """Initialize NoteManager with a client implementing ZoteroClientProtocol.

        Args:
            client: Any client implementing ZoteroClientProtocol (ZoteroClient or ZoteroClientRouter)
        """
        self.client = client

    async def create_note(
        self, item_key: str, content: str | dict[str, Any], tags: list[str] | None = None
    ) -> Note:
        """Create a new note for an item."""
        # Convert dict to string if needed
        match content:
            case dict():
                content_str = format_dict_to_html(content)
            case str():
                # Try to parse as JSON and convert to dict
                try:
                    content_dict = json.loads(content)
                    content_str = format_dict_to_html(content_dict)
                except (json.JSONDecodeError, ValueError):
                    content_str = content
            case _:
                content_str = str(content)

        note_item = ItemCreate(
            item_type="note",
            parent_item=item_key,
            note=format_note_html(content_str),
            tags=[ZoteroTag(tag=tag, type=1) for tag in (tags or [])],
        )

        created = await self.client.create_items([note_item])
        created_note = created[0]

        return Note(
            key=created_note.key,
            parent_key=item_key,
            content=content_str,
            created=datetime.now(),
            modified=datetime.now(),
            tags=tags or [],
        )

    async def get_notes_for_item(self, item_key: str) -> list[Note]:
        """Get all notes for a specific item."""
        children = await self.client.get_children(item_key)

        notes = []
        for child in children:
            if child.item_type == "note":
                notes.append(
                    Note(
                        key=child.key,
                        parent_key=item_key,
                        content=extract_note_text(child.data.get("note", "")),
                        created=parse_datetime(child.data.get("dateAdded", "")),
                        modified=parse_datetime(child.data.get("dateModified", "")),
                        tags=[tag["tag"] for tag in child.data.get("tags", [])],
                    )
                )

        return notes

    async def get_note(self, note_key: str) -> Note:
        """Get single note by key."""
        raw_note = await self.client.get_raw_item(note_key)
        return Note(
            key=raw_note["key"],
            parent_key=raw_note["data"].get("parentItem"),
            content=extract_note_text(raw_note["data"]["note"]),
            created=parse_datetime(raw_note["data"].get("dateAdded", "")),
            modified=parse_datetime(raw_note["data"].get("dateModified", "")),
            tags=[tag["tag"] for tag in raw_note["data"].get("tags", [])],
        )

    async def update_note(self, note_key: str, content: str | dict[str, Any]) -> Note:
        """Update existing note content."""
        # Convert dict to string if needed
        content_str = content if isinstance(content, str) else str(content)

        raw_note = await self.client.get_raw_item(note_key)

        update = ItemUpdate(note=format_note_html(content_str))
        await self.client.update_item(note_key, update)

        return Note(
            key=note_key,
            parent_key=raw_note["data"].get("parentItem"),
            content=content_str,
            created=parse_datetime(raw_note["data"].get("dateAdded", "")),
            modified=datetime.now(),
            tags=[tag["tag"] for tag in raw_note["data"].get("tags", [])],
        )

    async def search_notes(self, query: str) -> list[Note]:
        """Search through all notes."""
        # Simple search implementation
        all_items = await self.client.get_all_items()
        notes = []

        query_lower = query.lower()

        for item in all_items:
            if item["data"]["itemType"] == "note":
                note_text = extract_note_text(item["data"].get("note", ""))

                if query_lower in note_text.lower():
                    notes.append(
                        Note(
                            key=item["key"],
                            parent_key=item["data"].get("parentItem"),
                            content=note_text[:500],  # First 500 chars
                            created=parse_datetime(item["data"].get("dateAdded", "")),
                            modified=parse_datetime(item["data"].get("dateModified", "")),
                            tags=[tag["tag"] for tag in item["data"].get("tags", [])],
                        )
                    )

        return notes
