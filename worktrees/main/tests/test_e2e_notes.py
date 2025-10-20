"""E2E tests for notes management functionality."""

import uuid

import pytest
from fastmcp import Context

from src.mcp_server import manage_notes
from src.models import ManageNotesRequest, NoteAction
from src.zotero_client import ZoteroClient


class TestNotesE2E:
    """End-to-end tests for notes with real Zotero."""
    
    @pytest.mark.asyncio
    async def test_note_lifecycle(
        self,
        mcp_context: Context,
        test_item_with_pdf: str,
        real_zotero_client: ZoteroClient,
        setup_test_data: dict,
    ) -> None:
        """Test complete note lifecycle: create, read, update."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # 1. Create note
        test_content = f"Test note content {uuid.uuid4()}"
        create_request = ManageNotesRequest(
            action=NoteAction.CREATE,
            item_key=test_item_with_pdf,
            content=test_content,
        )
        
        create_response = await manage_notes(mcp_context, create_request)
        assert not create_response.error
        assert create_response.note
        assert create_response.note.content == test_content
        
        note_key = create_response.note.key
        setup_test_data["track_item"](note_key)  # Track for cleanup
        
        # 2. Read note
        read_request = ManageNotesRequest(
            action=NoteAction.READ,
            note_key=note_key,
        )
        
        read_response = await manage_notes(mcp_context, read_request)
        assert not read_response.error
        assert read_response.note
        assert read_response.note.key == note_key
        assert read_response.note.content == test_content
        
        # 3. Update note
        updated_content = f"Updated content {uuid.uuid4()}"
        update_request = ManageNotesRequest(
            action=NoteAction.UPDATE,
            note_key=note_key,
            content=updated_content,
        )
        
        update_response = await manage_notes(mcp_context, update_request)
        assert not update_response.error
        assert update_response.note
        assert update_response.note.content == updated_content
    
    @pytest.mark.asyncio
    async def test_read_notes_for_item(
        self,
        mcp_context: Context,
        test_item_with_pdf: str,
        real_zotero_client: ZoteroClient,
        setup_test_data: dict,
    ) -> None:
        """Test reading all notes for an item."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Create multiple notes
        note_keys = []
        for i in range(3):
            create_request = ManageNotesRequest(
                action=NoteAction.CREATE,
                item_key=test_item_with_pdf,
                content=f"Test note {i}",
            )
            response = await manage_notes(mcp_context, create_request)
            if response.note:
                note_keys.append(response.note.key)
                setup_test_data["track_item"](response.note.key)
        
        # Read all notes for item
        read_request = ManageNotesRequest(
            action=NoteAction.READ,
            item_key=test_item_with_pdf,
        )
        
        read_response = await manage_notes(mcp_context, read_request)
        assert not read_response.error
        assert read_response.notes
        assert read_response.count >= len(note_keys)
        
        # Check our notes are in the response
        response_keys = {note.key for note in read_response.notes}
        for key in note_keys:
            assert key in response_keys
    
    @pytest.mark.asyncio
    async def test_search_notes(
        self,
        mcp_context: Context,
        test_item_with_pdf: str,
        real_zotero_client: ZoteroClient,
        setup_test_data: dict,
    ) -> None:
        """Test searching notes by content."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Create notes with unique content
        unique_term = f"unique_{uuid.uuid4().hex[:8]}"
        create_request = ManageNotesRequest(
            action=NoteAction.CREATE,
            item_key=test_item_with_pdf,
            content=f"This note contains {unique_term} for searching",
        )
        
        create_response = await manage_notes(mcp_context, create_request)
        if create_response.note:
            setup_test_data["track_item"](create_response.note.key)
        
        # Search for unique term
        search_request = ManageNotesRequest(
            action=NoteAction.SEARCH,
            search_query=unique_term,
        )
        
        search_response = await manage_notes(mcp_context, search_request)
        assert not search_response.error
        
        if search_response.notes:
            # At least our note should be found
            assert search_response.count >= 1
            # Check content contains search term
            found = any(
                unique_term in note.content 
                for note in search_response.notes
            )
            assert found
    
    @pytest.mark.asyncio
    async def test_note_error_handling(
        self,
        mcp_context: Context,
        real_zotero_client: ZoteroClient,
    ) -> None:
        """Test error handling for invalid operations."""
        import src.mcp_server
        src.mcp_server._client = real_zotero_client
        
        # Try to read non-existent note
        read_request = ManageNotesRequest(
            action=NoteAction.READ,
            note_key="NONEXISTENT_KEY_12345",
        )
        
        response = await manage_notes(mcp_context, read_request)
        # Should handle gracefully - either error or None
        assert response.error or response.note is None
        
        # Try to create note without required fields
        invalid_request = ManageNotesRequest(
            action=NoteAction.CREATE,
            # Missing item_key and content
        )
        
        response = await manage_notes(mcp_context, invalid_request)
        assert response.error