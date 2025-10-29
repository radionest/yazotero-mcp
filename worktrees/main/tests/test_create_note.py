"""E2E tests for create_note_for_item endpoint."""

import json

import pytest
from fastmcp import Client

import src.zotero_client
from src.mcp_server import mcp
from src.zotero_client import ZoteroClient


class TestCreateNoteEndpoint:
    """End-to-end tests for create_note_for_item MCP endpoint."""

    @pytest.fixture
    async def test_item_for_note(
        self,
        test_data_manager,
        real_zotero_client: ZoteroClient,
    ) -> str:
        """Create a test item to attach notes to."""
        items = await test_data_manager.create_test_items(
            count=1,
            template_type="journalArticle",
        )
        return items[0].key

    # Basic Note Creation Tests

    @pytest.mark.asyncio
    async def test_create_note_with_plain_text(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test basic note creation with plain text content."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "Test Note"
        content = "This is a test note with plain text content."

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content,
                },
            )
            note = result.data

        # Verify note was created
        assert note is not None
        assert note.key
        assert note.parent_key == test_item_for_note
        assert title in note.content
        assert content in note.content

    @pytest.mark.asyncio
    async def test_create_note_with_dict_content(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test note creation with structured dictionary content (JSON-formatted)."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "Structured Analysis"
        content_dict = {
            "summary": "This article discusses...",
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "rating": 5,
        }

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content_dict,
                },
            )
            note = result.data

        # Verify note structure
        assert note is not None
        assert note.key
        assert note.parent_key == test_item_for_note
        assert title in note.content

        # Verify dict is JSON-formatted in content
        assert "summary" in note.content
        assert "key_points" in note.content
        assert "Point 1" in note.content

    @pytest.mark.asyncio
    async def test_create_note_with_tags(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test note creation with tags properly attached."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "Tagged Note"
        content = "Note with tags"
        tags = ["important", "review", "test"]

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content,
                    "tags": tags,
                },
            )
            note = result.data

        # Verify note has tags
        assert note is not None
        assert note.tags == tags
        assert len(note.tags) == 3
        assert "important" in note.tags
        assert "review" in note.tags

    @pytest.mark.asyncio
    async def test_create_note_without_tags(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test note creation without optional tags parameter."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "Untagged Note"
        content = "Note without tags"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content,
                },
            )
            note = result.data

        # Verify note was created without tags
        assert note is not None
        assert note.tags == []

    # Content Formatting Tests

    @pytest.mark.asyncio
    async def test_note_title_in_content(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that title is prepended to content as markdown heading."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "My Important Note"
        content = "Content of the note"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content,
                },
            )
            note = result.data

        # Verify title is in content as markdown header
        assert note.content.startswith(f"# {title}")
        assert content in note.content

    @pytest.mark.asyncio
    async def test_dict_content_json_formatting(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that dictionary content is properly JSON-formatted with indentation."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "Structured Note"
        content_dict = {
            "section_a": "Value A",
            "section_b": {"nested": "data"},
        }

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content_dict,
                },
            )
            note = result.data

        # Verify JSON formatting with indentation
        expected_json = json.dumps(content_dict, indent=2)
        assert expected_json in note.content

    # Note Structure Validation Tests

    @pytest.mark.asyncio
    async def test_created_note_structure(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that returned Note model has all required fields."""
        src.zotero_client.zotero_client = real_zotero_client

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": "Structure Test",
                    "content": "Testing structure",
                },
            )
            note = result.data

        # Verify all required Note fields
        assert hasattr(note, "key")
        assert hasattr(note, "parent_key")
        assert hasattr(note, "content")
        assert hasattr(note, "created")
        assert hasattr(note, "modified")
        assert hasattr(note, "tags")

        # Verify field types
        assert isinstance(note.key, str)
        assert isinstance(note.parent_key, str)
        assert isinstance(note.content, str)
        assert isinstance(note.tags, list)

    @pytest.mark.asyncio
    async def test_note_parent_relationship(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that note is correctly linked to parent item."""
        src.zotero_client.zotero_client = real_zotero_client

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": "Parent Test",
                    "content": "Testing parent relationship",
                },
            )
            note = result.data

        # Verify parent relationship
        assert note.parent_key == test_item_for_note

        # Verify note appears as child of parent item
        children = await real_zotero_client.get_children(test_item_for_note)
        note_keys = [child.key for child in children if child.item_type == "note"]
        assert note.key in note_keys

    @pytest.mark.asyncio
    async def test_note_has_valid_key(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that created note has a valid Zotero key."""
        src.zotero_client.zotero_client = real_zotero_client

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": "Key Test",
                    "content": "Testing key generation",
                },
            )
            note = result.data

        # Verify key format (Zotero keys are 8-character alphanumeric)
        assert note.key
        assert len(note.key) == 8
        assert note.key.isalnum()

    # Integration Tests

    @pytest.mark.asyncio
    async def test_multiple_notes_for_same_item(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test creating multiple notes for the same item."""
        src.zotero_client.zotero_client = real_zotero_client

        note_count = 3
        created_keys = []

        async with Client(mcp) as client:
            for i in range(note_count):
                result = await client.call_tool(
                    "create_note_for_item",
                    arguments={
                        "item_key": test_item_for_note,
                        "title": f"Note {i + 1}",
                        "content": f"Content for note {i + 1}",
                    },
                )
                note = result.data
                created_keys.append(note.key)

        # Verify all notes were created with unique keys
        assert len(created_keys) == note_count
        assert len(set(created_keys)) == note_count  # All keys are unique

        # Verify all notes are children of the item
        children = await real_zotero_client.get_children(test_item_for_note)
        child_note_keys = [child.key for child in children if child.item_type == "note"]
        for key in created_keys:
            assert key in child_note_keys

    # Error Handling Tests

    @pytest.mark.asyncio
    async def test_create_note_empty_content(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test handling of empty content string."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "Empty Content Note"
        content = ""

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content,
                },
            )
            note = result.data

        # Should still create note with title only
        assert note is not None
        assert note.key
        assert title in note.content

    @pytest.mark.asyncio
    async def test_create_note_empty_title(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test with empty title parameter."""
        src.zotero_client.zotero_client = real_zotero_client

        title = ""
        content = "Content without title"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content,
                },
            )
            note = result.data

        # Should still create note with content
        assert note is not None
        assert note.key
        assert content in note.content

    # Tag Handling Tests

    @pytest.mark.asyncio
    async def test_note_with_manual_tags(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test creating note with manual (type=1) tags."""
        src.zotero_client.zotero_client = real_zotero_client

        tags = ["manual-tag-1", "manual-tag-2"]

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": "Manual Tags",
                    "content": "Testing manual tags",
                    "tags": tags,
                },
            )
            note = result.data

        # Verify tags are stored as strings in Note model
        assert note.tags == tags
        assert all(isinstance(tag, str) for tag in note.tags)

    @pytest.mark.asyncio
    async def test_note_tags_properly_stored(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test that tags are persisted correctly in Zotero."""
        src.zotero_client.zotero_client = real_zotero_client

        tags = ["persistent-tag-1", "persistent-tag-2", "persistent-tag-3"]

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": "Persistent Tags",
                    "content": "Testing tag persistence",
                    "tags": tags,
                },
            )
            note = result.data

        # Retrieve the note from Zotero to verify persistence
        raw_note = await real_zotero_client.get_raw_item(note.key)
        stored_tags = [tag["tag"] for tag in raw_note["data"].get("tags", [])]

        # Verify all tags are stored
        for tag in tags:
            assert tag in stored_tags

    @pytest.mark.asyncio
    async def test_create_note_with_special_characters(
        self,
        test_item_for_note: str,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test note creation with special characters in content."""
        src.zotero_client.zotero_client = real_zotero_client

        title = "Special Characters Test"
        content = "Testing <HTML> & 'quotes' and \"double quotes\" with émojis 🎉"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": test_item_for_note,
                    "title": title,
                    "content": content,
                },
            )
            note = result.data

        # Note should be created and content preserved (HTML-escaped internally)
        assert note is not None
        assert note.key
        # Content should contain the original text (extract_note_text reverses HTML escaping)
        assert "HTML" in note.content
        assert "quotes" in note.content
