import json
from typing import TYPE_CHECKING, Any

from .exceptions import ZoteroError
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

    @staticmethod
    def _content_to_html(content: str | dict[str, Any]) -> tuple[str, str]:
        """Convert content to HTML for Zotero storage.

        Returns (content_str, note_html) where content_str is the plain text
        representation and note_html is the HTML for Zotero.
        """
        is_html = False
        match content:
            case dict():
                content_str = format_dict_to_html(content)
                is_html = True
            case str():
                try:
                    content_dict = json.loads(content)
                    content_str = format_dict_to_html(content_dict)
                    is_html = True
                except (json.JSONDecodeError, ValueError):
                    content_str = content
            case _:
                content_str = str(content)

        note_html = content_str if is_html else format_note_html(content_str)
        return content_str, note_html

    async def create_note(
        self, item_key: str, content: str | dict[str, Any], tags: list[str] | None = None
    ) -> Note:
        """Create a new note for an item."""
        content_str, note_html = self._content_to_html(content)
        note_item = ItemCreate(
            item_type="note",
            parent_item=item_key,
            note=note_html,
            tags=[ZoteroTag(tag=tag, type=1) for tag in (tags or [])],
        )

        created = await self.client.create_items([note_item])
        if not created:
            raise ZoteroError(
                f"Failed to create note for item '{item_key}': API returned empty response. "
                "Hint: verify the item key exists and web API credentials have write permissions."
            )
        created_note = created[0]

        return Note(
            key=created_note.key,
            parent_key=item_key,
            content=content_str,
            created=parse_datetime(created_note.data.date_added),
            modified=parse_datetime(created_note.data.date_modified),
            tags=tags or [],
        )

    async def update_note(self, note_key: str, content: str | dict[str, Any]) -> Note:
        """Update an existing note's content in-place."""
        _, note_html = self._content_to_html(content)
        await self.client.update_item(note_key, ItemUpdate(note=note_html))
        return await self.get_note(note_key)

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
