"""Tests for fulltext extraction from PDF attachments."""

import json

import pytest
from fastmcp import Client

from yazot.mcp_server import mcp
from yazot.zotero_client import ZoteroClient


class TestFulltextExtraction:
    """Test fulltext extraction against a self-contained item with uploaded PDF."""

    @pytest.mark.asyncio
    async def test_get_children_returns_pdf_attachment(
        self,
        test_zotero_client: ZoteroClient,
        item_with_pdf_key: str,
    ) -> None:
        """get_children returns the PDF attachment uploaded by the fixture."""
        children = await test_zotero_client.get_children(item_with_pdf_key)

        assert len(children) > 0, "Item should have child attachments"

        pdf_attachments = [c for c in children if c.content_type == "application/pdf"]
        assert len(pdf_attachments) > 0, "Item should have at least one PDF attachment"

        pdf = pdf_attachments[0]
        assert pdf.key
        assert pdf.item_type == "attachment"
        assert pdf.filename

    @pytest.mark.asyncio
    async def test_get_pdf_text_extraction(
        self,
        test_zotero_client: ZoteroClient,
        item_with_pdf_key: str,
    ) -> None:
        """get_pdf_text downloads and extracts text from the uploaded PDF."""
        pdf_text = await test_zotero_client.get_pdf_text(item_with_pdf_key)

        assert pdf_text is not None, "PDF text should be available"
        assert isinstance(pdf_text, str)
        assert len(pdf_text) > 0, "PDF text should not be empty"
        assert "test PDF document" in pdf_text or "YAZot" in pdf_text

    @pytest.mark.asyncio
    async def test_get_pdf_text_cache_behavior(
        self,
        test_zotero_client: ZoteroClient,
        item_with_pdf_key: str,
    ) -> None:
        """PDF text results are cached after first fetch."""
        pdf_text1 = await test_zotero_client.get_pdf_text(item_with_pdf_key)

        cache_key = f"pdf_text:{item_with_pdf_key}"
        assert cache_key in test_zotero_client.cache, "PDF text should be cached"

        pdf_text2 = await test_zotero_client.get_pdf_text(item_with_pdf_key)
        assert pdf_text1 == pdf_text2, "Cached PDF text should match"

    @pytest.mark.asyncio
    async def test_get_fulltext_from_indexed_or_none(
        self,
        test_zotero_client: ZoteroClient,
        item_with_pdf_key: str,
    ) -> None:
        """get_fulltext returns indexed text or None for a freshly uploaded PDF.

        Zotero may not have indexed the PDF yet, so None is acceptable.
        If it returns something, it must be a non-empty string.
        """
        fulltext = await test_zotero_client.get_fulltext(item_with_pdf_key)

        if fulltext is not None:
            assert isinstance(fulltext, str)
            assert len(fulltext) > 0

    @pytest.mark.asyncio
    async def test_fulltext_fallback_to_pdf_text(
        self,
        test_zotero_client: ZoteroClient,
        item_with_pdf_key: str,
    ) -> None:
        """At least one extraction method (fulltext or pdf_text) returns content."""
        fulltext = await test_zotero_client.get_fulltext(item_with_pdf_key)
        pdf_text = await test_zotero_client.get_pdf_text(item_with_pdf_key)

        # pdf_text should always work since we uploaded the PDF ourselves
        assert pdf_text is not None, "PDF text should be available"
        assert len(pdf_text) > 0

        # At least one should succeed
        assert fulltext is not None or pdf_text is not None


class TestMCPFulltextEndpoint:
    """Test get_item_fulltext MCP endpoint with self-contained test data."""

    @pytest.mark.asyncio
    async def test_get_item_fulltext_basic(
        self,
        item_with_pdf_key: str,
    ) -> None:
        """get_item_fulltext returns content for the test item."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_item_fulltext",
                arguments={"item_key": item_with_pdf_key},
            )
            response = result.data

        assert response.item_key == item_with_pdf_key
        assert response.content is not None
        assert isinstance(response.content, str)
        assert len(response.content) > 0
        assert response.has_more is not None

    @pytest.mark.asyncio
    async def test_get_item_fulltext_token_limit_compliance(
        self,
        item_with_pdf_key: str,
    ) -> None:
        """get_item_fulltext responses stay under MCP 25000 token limit."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_item_fulltext",
                arguments={"item_key": item_with_pdf_key},
            )
            response = result.data

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

        response_tokens = len(response_json) // 4
        assert (
            response_tokens < 25000
        ), f"Response exceeds MCP token limit: {response_tokens} tokens"

    @pytest.mark.asyncio
    async def test_get_item_fulltext_chunking_workflow(
        self,
        item_with_pdf_key: str,
        chunker_with_small_size: int,
    ) -> None:
        """Fulltext chunking workflow — small chunk size forces multiple chunks."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_item_fulltext",
                arguments={"item_key": item_with_pdf_key},
            )
            response = result.data

            all_content = response.content
            chunk_count = 1

            while response.has_more:
                chunk_id = response.chunk_id
                assert chunk_id is not None, "chunk_id should be present when has_more=True"

                result = await client.call_tool(
                    "get_next_fulltext_chunk",
                    arguments={"chunk_id": chunk_id},
                )
                response = result.data

                assert response.content is not None
                assert response.item_key == item_with_pdf_key
                assert response.current_chunk is not None
                assert response.total_chunks is not None
                assert response.current_chunk <= response.total_chunks

                all_content += response.content
                chunk_count += 1

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

            assert len(all_content) > 0
