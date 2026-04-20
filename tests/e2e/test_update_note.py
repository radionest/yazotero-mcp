"""E2E tests for update_note_for_item endpoint."""

import pytest
from fastmcp import Client

from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient


class TestUpdateNoteEndpoint:
    @pytest.fixture
    async def created_note(
        self,
        test_data_manager,
        test_zotero_client: ZoteroClient,
    ) -> dict:
        """Create a test item with a note, return both keys."""
        items = await test_data_manager.create_test_items(
            count=1,
            template_type="journalArticle",
        )
        item_key = items[0].key

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": item_key,
                    "title": "Original Title",
                    "content": "Original content before update.",
                },
            )
            note = result.data

        return {"item_key": item_key, "note_key": note.key}

    @pytest.mark.asyncio
    async def test_update_note_replaces_content(self, created_note: dict) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_note_for_item",
                arguments={
                    "note_key": created_note["note_key"],
                    "content": "# Updated Title\n\nNew content after update.",
                },
            )
            note = result.data

        assert note.key == created_note["note_key"]
        assert "New content after update" in note.content
        assert "Original content" not in note.content

    @pytest.mark.asyncio
    async def test_update_note_preserves_parent(self, created_note: dict) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_note_for_item",
                arguments={
                    "note_key": created_note["note_key"],
                    "content": "Updated content.",
                },
            )
            note = result.data

        assert note.parent_key == created_note["item_key"]

    @pytest.mark.asyncio
    async def test_update_note_preserves_tags(
        self, created_note: dict, test_zotero_client: ZoteroClient
    ) -> None:
        # First add tags via update_item_tags
        async with Client(mcp) as client:
            await client.call_tool(
                "update_item_tags",
                arguments={
                    "item_key": created_note["note_key"],
                    "tags": ["important", "review"],
                    "mode": "add",
                },
            )

            # Now update note content
            result = await client.call_tool(
                "update_note_for_item",
                arguments={
                    "note_key": created_note["note_key"],
                    "content": "Content updated, tags should remain.",
                },
            )
            note = result.data

        assert "important" in note.tags
        assert "review" in note.tags

    @pytest.mark.asyncio
    async def test_update_note_with_dict_content(self, created_note: dict) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "update_note_for_item",
                arguments={
                    "note_key": created_note["note_key"],
                    "content": {"summary": "Updated analysis", "rating": 5},
                },
            )
            note = result.data

        assert "summary" in note.content
        assert "Updated analysis" in note.content
