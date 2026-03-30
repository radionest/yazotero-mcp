"""E2E tests for fetch_external_fulltext MCP tool.

Tests the full MCP tool flow via Client(mcp), mocking external HTTP calls
(Unpaywall/CORE/Libgen) while using real MCP lifespan and TextChunker.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pypdf import PdfWriter

from yazot.mcp_server import mcp


def _make_pdf_bytes(pages: int = 1, text: str = "Sample text") -> bytes:
    """Create valid PDF bytes. Text extraction is mocked separately."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestFetchExternalFulltext:
    """E2E tests for fetch_external_fulltext via Client(mcp)."""

    @pytest.fixture(autouse=True)
    def _setup_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Configure env for external fulltext resolver."""
        monkeypatch.setenv("UNPAYWALL_EMAIL", "test@example.com")
        monkeypatch.setenv("CORE_API_KEY", "test-core-key")

    @pytest.mark.asyncio
    async def test_fetch_by_doi_returns_text(self) -> None:
        """Basic flow: DOI → Unpaywall → download PDF → extract text."""
        pdf_bytes = _make_pdf_bytes()

        with (
            patch(
                "yazot.fulltext_resolver.UnpaywallClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value="https://example.com/paper.pdf",
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.download",
                new_callable=AsyncMock,
                return_value=pdf_bytes,
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.extract_text",
                return_value="This is the extracted fulltext content from the PDF.",
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={"doi": "10.1234/test"},
                )
                response = result.data

        assert response.content == "This is the extracted fulltext content from the PDF."
        assert response.source == "unpaywall"
        assert response.error is None
        assert response.item_key is None

    @pytest.mark.asyncio
    async def test_fetch_by_title_returns_text(self) -> None:
        """Search by title when no DOI provided — falls through to CORE."""
        pdf_bytes = _make_pdf_bytes()

        with (
            patch(
                "yazot.fulltext_resolver.CoreClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value="https://core.ac.uk/download/pdf/123.pdf",
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.download",
                new_callable=AsyncMock,
                return_value=pdf_bytes,
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.extract_text",
                return_value="Extracted text from CORE source.",
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={"title": "Machine Learning in Medicine"},
                )
                response = result.data

        assert response.content == "Extracted text from CORE source."
        assert response.source == "core"

    @pytest.mark.asyncio
    async def test_cascade_unpaywall_fails_core_succeeds(self) -> None:
        """Unpaywall returns None → fallback to CORE."""
        pdf_bytes = _make_pdf_bytes()

        with (
            patch(
                "yazot.fulltext_resolver.UnpaywallClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "yazot.fulltext_resolver.CoreClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value="https://core.ac.uk/pdf/456.pdf",
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.download",
                new_callable=AsyncMock,
                return_value=pdf_bytes,
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.extract_text",
                return_value="Content from CORE after Unpaywall miss.",
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={"doi": "10.1234/closed-access", "title": "Closed Paper"},
                )
                response = result.data

        assert response.source == "core"
        assert "Content from CORE" in response.content

    @pytest.mark.asyncio
    async def test_all_sources_fail_raises_error(self) -> None:
        """All sources return None → FulltextNotFoundError shown to client."""
        with (
            patch(
                "yazot.fulltext_resolver.UnpaywallClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "yazot.fulltext_resolver.CoreClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ToolError, match="No fulltext found"),
        ):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={"doi": "10.9999/nonexistent"},
                )

    @pytest.mark.asyncio
    async def test_no_doi_no_title_raises_error(self) -> None:
        """Neither doi nor title provided → ZoteroError."""
        with pytest.raises(ToolError, match="At least one of doi or title"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={},
                )

    @pytest.mark.asyncio
    async def test_empty_text_extraction_returns_error(self) -> None:
        """PDF downloads OK but text extraction yields empty string."""
        pdf_bytes = _make_pdf_bytes()

        with (
            patch(
                "yazot.fulltext_resolver.UnpaywallClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value="https://example.com/scanned.pdf",
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.download",
                new_callable=AsyncMock,
                return_value=pdf_bytes,
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.extract_text",
                return_value="   ",
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={"doi": "10.1234/scanned"},
                )
                response = result.data

        assert response.content == ""
        assert response.error is not None
        assert "no text" in response.error.lower()

    @pytest.mark.asyncio
    async def test_chunking_with_large_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Large text is chunked and retrievable via get_next_fulltext_chunk."""
        monkeypatch.setenv("MAX_CHUNK_SIZE", "100")
        # Generate text larger than 100 tokens (400+ chars)
        large_text = "This is paragraph one. " * 50 + "\n\n" + "Second paragraph here. " * 50
        pdf_bytes = _make_pdf_bytes()

        with (
            patch(
                "yazot.fulltext_resolver.UnpaywallClient.find_pdf_url",
                new_callable=AsyncMock,
                return_value="https://example.com/large.pdf",
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.download",
                new_callable=AsyncMock,
                return_value=pdf_bytes,
            ),
            patch(
                "yazot.fulltext_resolver.FulltextResolver.extract_text",
                return_value=large_text,
            ),
        ):
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={"doi": "10.1234/large"},
                )
                response = result.data

                assert response.has_more is True
                assert response.chunk_id is not None
                assert response.source == "unpaywall"
                assert "get_next_fulltext_chunk" in (response.message or "")

                # Retrieve all remaining chunks
                all_content = response.content
                while response.has_more:
                    chunk_result = await client.call_tool(
                        "get_next_fulltext_chunk",
                        arguments={"chunk_id": response.chunk_id},
                    )
                    response = chunk_result.data
                    all_content += response.content

        # Reassembled content should match original
        assert len(all_content) > 0
        assert "paragraph one" in all_content
        assert "Second paragraph" in all_content


class TestFetchExternalFulltextNotConfigured:
    """Tests when no external sources are configured."""

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ensure no external fulltext config is set."""
        monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
        monkeypatch.delenv("CORE_API_KEY", raising=False)
        monkeypatch.delenv("FULLTEXT_LIBGEN_ENABLED", raising=False)

    @pytest.mark.asyncio
    async def test_not_configured_raises_error(self) -> None:
        """Tool raises ConfigurationError when no sources configured."""
        with pytest.raises(ToolError, match="not configured"):
            async with Client(mcp) as client:
                await client.call_tool(
                    "fetch_external_fulltext",
                    arguments={"doi": "10.1234/test"},
                )
