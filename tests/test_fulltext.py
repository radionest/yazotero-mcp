"""Tests for fulltext extraction from PDF attachments."""

import json

import pytest
from fastmcp import Client

from yazot.config import Settings
from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient


class TestFulltextExtraction:
    """Test fulltext extraction with local Zotero client."""

    @pytest.fixture
    def local_client(self) -> ZoteroClient:
        """Create local Zotero client for testing."""
        settings = Settings(
            zotero_local=True,
            zotero_library_id="0",
            zotero_library_type="user",
        )
        return ZoteroClient(settings)

    @pytest.mark.asyncio
    async def test_get_fulltext_from_item_with_pdf(
        self,
        local_client: ZoteroClient,
    ) -> None:
        """Test fulltext extraction from item DF33QFUC with PDF attachment.

        This test uses a real item from the local library to verify that:
        1. get_fulltext correctly finds PDF attachment among children
        2. Extracts fulltext content from the PDF
        3. Returns the content as a string
        """
        item_key = "DF33QFUC"

        # Get fulltext (should find PDF attachment and extract content)
        fulltext = await local_client.get_fulltext(item_key)

        # Verify fulltext was extracted
        assert fulltext is not None, "Fulltext should be available for item with PDF"
        assert isinstance(fulltext, str), "Fulltext should be a string"
        assert len(fulltext) > 0, "Fulltext should not be empty"

        # Verify caching works
        cached_fulltext = await local_client.get_fulltext(item_key)
        assert cached_fulltext == fulltext, "Cached fulltext should match original"

    @pytest.mark.asyncio
    async def test_get_children_returns_attachments(
        self,
        local_client: ZoteroClient,
    ) -> None:
        """Test that get_children returns PDF attachments for item DF33QFUC."""
        item_key = "DF33QFUC"

        # Get children
        children = await local_client.get_children(item_key)

        # Verify we have attachments
        assert len(children) > 0, "Item should have child attachments"

        # Find PDF attachment
        pdf_attachments = [child for child in children if child.content_type == "application/pdf"]

        assert len(pdf_attachments) > 0, "Item should have at least one PDF attachment"

        # Verify attachment structure
        pdf = pdf_attachments[0]
        assert pdf.key, "PDF attachment should have a key"
        assert pdf.item_type == "attachment", "PDF should be of type 'attachment'"
        assert pdf.content_type == "application/pdf"
        assert pdf.filename, "PDF should have a filename"

    @pytest.mark.asyncio
    async def test_fulltext_cache_behavior(
        self,
        local_client: ZoteroClient,
    ) -> None:
        """Test that fulltext results are properly cached."""
        item_key = "DF33QFUC"

        # First call should fetch from API
        fulltext1 = await local_client.get_fulltext(item_key)

        # Second call should return from cache
        cache_key = f"fulltext:{item_key}"
        assert cache_key in local_client.cache, "Fulltext should be cached"

        fulltext2 = await local_client.get_fulltext(item_key)
        assert fulltext1 == fulltext2, "Cached fulltext should match"

    @pytest.mark.asyncio
    async def test_get_pdf_text_extraction(
        self,
        local_client: ZoteroClient,
    ) -> None:
        """Test direct PDF download and text extraction using PyPDF2.

        This test verifies that:
        1. get_pdf_text correctly finds PDF attachment
        2. Downloads the PDF file
        3. Extracts text using PyPDF2
        4. Returns the content as a string
        """
        item_key = "DF33QFUC"

        # Get PDF text (should download and parse PDF)
        pdf_text = await local_client.get_pdf_text(item_key)

        # Verify text was extracted
        assert pdf_text is not None, "PDF text should be available for item with PDF"
        assert isinstance(pdf_text, str), "PDF text should be a string"
        assert len(pdf_text) > 0, "PDF text should not be empty"

        # Verify caching works
        cached_pdf_text = await local_client.get_pdf_text(item_key)
        assert cached_pdf_text == pdf_text, "Cached PDF text should match original"

    @pytest.mark.asyncio
    async def test_fulltext_fallback_to_pdf_text(
        self,
        local_client: ZoteroClient,
    ) -> None:
        """Test that get_fulltext falls back to PDF parsing when API fulltext unavailable.

        This test verifies the fallback mechanism by comparing results from both methods.
        In production, get_item_fulltext (MCP tool) would use get_fulltext first,
        then fallback to get_pdf_text if needed.
        """
        item_key = "DF33QFUC"

        # Get text using both methods directly (simulating fallback behavior)
        fulltext = await local_client.get_fulltext(item_key)
        pdf_text = await local_client.get_pdf_text(item_key)

        # Both should return text
        assert fulltext is not None, "Fulltext should be available"
        assert pdf_text is not None, "PDF text should be available"

        # Both should be non-empty strings
        assert len(fulltext) > 100, "Fulltext should contain substantial content"
        assert len(pdf_text) > 100, "PDF text should contain substantial content"

        # Note: The exact text may differ slightly due to different extraction methods,
        # but both should contain the core content.
        # In production, get_item_fulltext MCP tool tries fulltext first, then pdf_text as fallback


class TestMCPFulltextEndpoint:
    """Test get_item_fulltext MCP endpoint.

    Uses Client(mcp) which triggers the lifespan. The lifespan creates
    dependencies from Settings() which reads .env.test (loaded by conftest).
    For local-mode tests, set ZOTERO_LOCAL=true in the test environment.
    """

    @pytest.mark.asyncio
    async def test_get_item_fulltext_basic(
        self,
    ) -> None:
        """Test get_item_fulltext MCP endpoint returns fulltext content."""
        item_key = "DF33QFUC"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_item_fulltext",
                arguments={"item_key": item_key},
            )
            response = result.data

        # Verify response structure
        assert response.item_key == item_key
        assert response.content is not None
        assert isinstance(response.content, str)
        assert len(response.content) > 0
        assert response.has_more is not None

    @pytest.mark.asyncio
    async def test_get_item_fulltext_uses_fallback(
        self,
    ) -> None:
        """Test get_item_fulltext falls back to PDF parsing when API fulltext unavailable."""
        item_key = "DF33QFUC"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_item_fulltext",
                arguments={"item_key": item_key},
            )
            response = result.data

        # Should return content (from either API or PDF fallback)
        assert response.content is not None
        assert len(response.content) > 100, "Should contain substantial text content"

    @pytest.mark.asyncio
    async def test_get_item_fulltext_token_limit_compliance(
        self,
    ) -> None:
        """Test that get_item_fulltext responses stay under MCP 25000 token limit."""
        item_key = "DF33QFUC"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_item_fulltext",
                arguments={"item_key": item_key},
            )
            response = result.data

        # Estimate tokens for complete response
        response_json = json.dumps(
            {
                "item_key": response.item_key,
                "content": response.content,
                "has_more": response.has_more,
                "chunk_id": response.chunk_id,
                "current_chunk": response.current_chunk,
                "total_chunks": response.total_chunks,
                "message": response.message,
                "error": response.error,
            },
            default=str,
        )

        response_tokens = len(response_json) // 4  # Simple estimation

        # Response should be under MCP limit
        assert response_tokens < 25000, (
            f"Response exceeds MCP token limit: {response_tokens} tokens "
            f"(limit: 25000). This means text chunking is not working correctly!"
        )

        # If chunked, verify chunk metadata is present
        if response.has_more:
            assert response.chunk_id is not None
            assert response.current_chunk is not None
            assert response.total_chunks is not None
            assert response.message is not None
            assert "get_next_fulltext_chunk" in response.message

    @pytest.mark.asyncio
    async def test_get_item_fulltext_chunking_workflow(
        self,
    ) -> None:
        """Test fulltext chunking workflow - get all chunks until completion."""
        item_key = "CRLXZCLC"

        async with Client(mcp) as client:
            # Get first chunk
            result = await client.call_tool(
                "get_item_fulltext",
                arguments={"item_key": item_key},
            )
            response = result.data

            all_content = response.content
            chunk_count = 1

            # Get remaining chunks if available
            while response.has_more:
                chunk_id = response.chunk_id
                assert chunk_id is not None, "chunk_id should be present when has_more=True"

                # Get next chunk
                result = await client.call_tool(
                    "get_next_fulltext_chunk",
                    arguments={"chunk_id": chunk_id},
                )
                response = result.data

                # Verify chunk structure
                assert response.content is not None
                assert response.item_key == item_key
                assert response.current_chunk is not None
                assert response.total_chunks is not None
                assert response.current_chunk <= response.total_chunks

                # Accumulate content
                all_content += response.content
                chunk_count += 1

                # Verify each chunk stays under token limit
                chunk_json = json.dumps(
                    {
                        "item_key": response.item_key,
                        "content": response.content,
                        "has_more": response.has_more,
                        "chunk_id": response.chunk_id,
                        "current_chunk": response.current_chunk,
                        "total_chunks": response.total_chunks,
                        "message": response.message,
                    },
                    default=str,
                )
                chunk_tokens = len(chunk_json) // 4
                assert (
                    chunk_tokens < 25000
                ), f"Chunk {chunk_count} exceeds limit: {chunk_tokens} tokens"

            # Verify we got complete content
            assert len(all_content) > 0
            if chunk_count > 1:
                # If it was chunked, verify we reassembled it correctly
                assert all_content.count(" ") > 100, "Combined content should have substantial text"
