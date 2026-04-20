"""Tests for external fulltext resolver — Unpaywall, CORE clients + cascade."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pypdf import PdfWriter

from tests.conftest import make_httpx_response
from yazot.exceptions import (
    FulltextDownloadError,
    FulltextNotFoundError,
    FulltextSourceError,
)
from yazot.fulltext_resolver import (
    CoreClient,
    FulltextResolver,
    UnpaywallClient,
)
from yazot.fulltext_source import FulltextSource

# --- Helpers ---


def make_pdf_bytes() -> bytes:
    """Create minimal valid PDF bytes for testing."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_mock_source(
    name: str = "mock", description: str = "Mock source", return_url: str | None = None
) -> FulltextSource:
    """Create a mock FulltextSource."""
    source = MagicMock(spec=FulltextSource)
    source.name = name
    source.description = description
    source.find_pdf_url = AsyncMock(return_value=return_url)
    source.aclose = AsyncMock()
    return source


# --- UnpaywallClient tests ---


class TestUnpaywallClient:
    @pytest.fixture
    def client(self) -> UnpaywallClient:
        return UnpaywallClient(email="test@example.com")

    def test_name_and_description(self, client: UnpaywallClient) -> None:
        assert client.name == "unpaywall"
        assert "Unpaywall" in client.description

    async def test_find_pdf_url_success(self, client: UnpaywallClient) -> None:
        response_data = {
            "doi": "10.1234/test",
            "is_oa": True,
            "best_oa_location": {
                "url_for_pdf": "https://example.com/paper.pdf",
                "url": "https://example.com/paper",
                "is_best": True,
            },
            "oa_locations": [],
        }
        mock_response = make_httpx_response(json_data=response_data)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url(doi="10.1234/test")

        assert url == "https://example.com/paper.pdf"

    async def test_find_pdf_url_fallback_to_oa_locations(self, client: UnpaywallClient) -> None:
        response_data = {
            "doi": "10.1234/test",
            "is_oa": True,
            "best_oa_location": {"url_for_pdf": None, "url": "https://example.com"},
            "oa_locations": [
                {"url_for_pdf": None},
                {"url_for_pdf": "https://archive.org/paper.pdf"},
            ],
        }
        mock_response = make_httpx_response(json_data=response_data)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url(doi="10.1234/test")

        assert url == "https://archive.org/paper.pdf"

    async def test_find_pdf_url_not_found(self, client: UnpaywallClient) -> None:
        mock_response = make_httpx_response(status_code=404)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url(doi="10.1234/nonexistent")

        assert url is None

    async def test_find_pdf_url_no_oa(self, client: UnpaywallClient) -> None:
        response_data = {
            "doi": "10.1234/closed",
            "is_oa": False,
            "best_oa_location": None,
            "oa_locations": [],
        }
        mock_response = make_httpx_response(json_data=response_data)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url(doi="10.1234/closed")

        assert url is None

    async def test_find_pdf_url_no_doi_returns_none(self, client: UnpaywallClient) -> None:
        url = await client.find_pdf_url(title="Some Title")
        assert url is None

    async def test_find_pdf_url_server_error(self, client: UnpaywallClient) -> None:
        mock_response = make_httpx_response(status_code=500)

        with (
            patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextSourceError, match="Unpaywall"),
        ):
            await client.find_pdf_url(doi="10.1234/test")


# --- CoreClient tests ---


class TestCoreClient:
    @pytest.fixture
    def client(self) -> CoreClient:
        return CoreClient(api_key="test-key")

    def test_name_and_description(self, client: CoreClient) -> None:
        assert client.name == "core"
        assert "CORE" in client.description

    async def test_find_pdf_url_by_doi(self, client: CoreClient) -> None:
        response_data = {
            "totalHits": 1,
            "results": [
                {
                    "id": 12345,
                    "doi": "10.1234/test",
                    "downloadUrl": "https://core.ac.uk/download/pdf/12345.pdf",
                    "title": "Test Article",
                }
            ],
        }
        mock_response = make_httpx_response(json_data=response_data)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url(doi="10.1234/test")

        assert url == "https://core.ac.uk/download/pdf/12345.pdf"

    async def test_find_pdf_url_by_title(self, client: CoreClient) -> None:
        response_data = {
            "totalHits": 1,
            "results": [
                {
                    "id": 67890,
                    "downloadUrl": "https://core.ac.uk/download/pdf/67890.pdf",
                    "title": "Machine Learning Paper",
                }
            ],
        }
        mock_response = make_httpx_response(json_data=response_data)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url(title="Machine Learning Paper")

        assert url == "https://core.ac.uk/download/pdf/67890.pdf"

    async def test_find_pdf_url_no_results(self, client: CoreClient) -> None:
        response_data = {"totalHits": 0, "results": []}
        mock_response = make_httpx_response(json_data=response_data)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url(doi="10.1234/nothing")

        assert url is None

    async def test_find_pdf_url_no_query(self, client: CoreClient) -> None:
        url = await client.find_pdf_url()
        assert url is None

    async def test_find_pdf_url_server_error(self, client: CoreClient) -> None:
        mock_response = make_httpx_response(status_code=500)

        with (
            patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextSourceError, match="CORE"),
        ):
            await client.find_pdf_url(doi="10.1234/test")


# --- FulltextResolver tests ---


class TestFulltextResolver:
    def test_is_configured_with_sources(self) -> None:
        source = make_mock_source()
        resolver = FulltextResolver([source])
        assert resolver.is_configured is True

    def test_is_configured_empty(self) -> None:
        resolver = FulltextResolver([])
        assert resolver.is_configured is False

    def test_sources_property(self) -> None:
        s1 = make_mock_source("a")
        s2 = make_mock_source("b")
        resolver = FulltextResolver([s1, s2])
        assert len(resolver.sources) == 2
        assert resolver.sources[0].name == "a"

    async def test_cascade_first_source_succeeds(self) -> None:
        s1 = make_mock_source("first", return_url="https://pdf.com/a.pdf")
        s2 = make_mock_source("second")
        resolver = FulltextResolver([s1, s2])

        url, source = await resolver.resolve("10.1234/test", "Test Title")

        assert url == "https://pdf.com/a.pdf"
        assert source == "first"
        s2.find_pdf_url.assert_not_called()

    async def test_cascade_fallback_to_second(self) -> None:
        s1 = make_mock_source("first", return_url=None)
        s2 = make_mock_source("second", return_url="https://core.ac.uk/pdf.pdf")
        resolver = FulltextResolver([s1, s2])

        url, source = await resolver.resolve("10.1234/test", "Test Title")

        assert url == "https://core.ac.uk/pdf.pdf"
        assert source == "second"

    async def test_cascade_all_fail(self) -> None:
        s1 = make_mock_source("first", return_url=None)
        s2 = make_mock_source("second", return_url=None)
        resolver = FulltextResolver([s1, s2])

        with pytest.raises(FulltextNotFoundError):
            await resolver.resolve("10.1234/test", "Test Title")

    async def test_cascade_error_continues(self) -> None:
        """Source errors are non-fatal — cascade continues."""
        s1 = make_mock_source("failing")
        s1.find_pdf_url = AsyncMock(side_effect=FulltextSourceError("failing", "timeout"))
        s2 = make_mock_source("working", return_url="https://core.ac.uk/pdf.pdf")
        resolver = FulltextResolver([s1, s2])

        url, source = await resolver.resolve("10.1234/test", "Test Title")

        assert source == "working"

    async def test_cascade_generic_exception_continues(self) -> None:
        """Generic exceptions from plugins don't break the cascade."""
        s1 = make_mock_source("buggy_plugin")
        s1.find_pdf_url = AsyncMock(side_effect=ValueError("plugin bug"))
        s2 = make_mock_source("working", return_url="https://example.com/pdf.pdf")
        resolver = FulltextResolver([s1, s2])

        url, source = await resolver.resolve("10.1234/test", None)

        assert source == "working"
        assert url == "https://example.com/pdf.pdf"

    async def test_resolve_empty_string_doi_normalized(self) -> None:
        """Empty/whitespace DOI and title are normalized to None → raises."""
        resolver = FulltextResolver([make_mock_source()])

        with pytest.raises(FulltextNotFoundError):
            await resolver.resolve("", "")

    async def test_resolve_whitespace_only_normalized(self) -> None:
        """Whitespace-only strings are normalized to None → raises."""
        resolver = FulltextResolver([make_mock_source()])

        with pytest.raises(FulltextNotFoundError):
            await resolver.resolve("  ", "  \n ")

    async def test_cascade_title_only(self) -> None:
        s1 = make_mock_source("source", return_url="https://example.com/pdf.pdf")
        resolver = FulltextResolver([s1])

        url, source = await resolver.resolve(None, "Test Title")

        assert url == "https://example.com/pdf.pdf"
        s1.find_pdf_url.assert_called_once_with(title="Test Title")

    async def test_cascade_doi_and_title(self) -> None:
        s1 = make_mock_source("source", return_url="https://example.com/pdf.pdf")
        resolver = FulltextResolver([s1])

        await resolver.resolve("10.1234/test", "Test Title")

        s1.find_pdf_url.assert_called_once_with(doi="10.1234/test", title="Test Title")

    async def test_download_success(self) -> None:
        resolver = FulltextResolver([])
        pdf_bytes = make_pdf_bytes()
        mock_response = make_httpx_response(
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )

        with patch.object(
            resolver._http, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await resolver.download("https://example.com/paper.pdf")

        assert result == pdf_bytes

    async def test_download_wrong_content_type(self) -> None:
        resolver = FulltextResolver([])
        mock_response = make_httpx_response(
            content=b"<html>Not a PDF</html>",
            headers={"content-type": "text/html"},
        )

        with (
            patch.object(resolver._http, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextDownloadError, match="content-type"),
        ):
            await resolver.download("https://example.com/not-a-pdf")

    async def test_download_empty_pdf_body(self) -> None:
        resolver = FulltextResolver([])
        mock_response = make_httpx_response(
            content=b"",
            headers={"content-type": "application/pdf"},
        )

        with (
            patch.object(resolver._http, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextDownloadError, match="Empty response body"),
        ):
            await resolver.download("https://example.com/empty.pdf")

    async def test_download_http_error(self) -> None:
        resolver = FulltextResolver([])
        mock_response = make_httpx_response(status_code=403)

        with (
            patch.object(resolver._http, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextDownloadError, match="HTTP 403"),
        ):
            await resolver.download("https://example.com/forbidden.pdf")

    def test_extract_text(self) -> None:
        resolver = FulltextResolver([])
        pdf_bytes = make_pdf_bytes()

        with patch("yazot.pdf_utils.PdfReader") as mock_reader_cls:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Page 1 text"
            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_cls.return_value = mock_reader

            text = resolver.extract_text(pdf_bytes)

        assert text == "Page 1 text"

    def test_extract_text_pdf_parse_failure(self) -> None:
        from pypdf.errors import PdfReadError

        resolver = FulltextResolver([])
        pdf_bytes = make_pdf_bytes()

        with (
            patch(
                "yazot.pdf_utils.PdfReader",
                side_effect=PdfReadError("corrupt"),
            ),
            pytest.raises(FulltextDownloadError, match="Failed to parse PDF"),
        ):
            resolver.extract_text(pdf_bytes)

    def test_extract_text_multiple_pages(self) -> None:
        resolver = FulltextResolver([])
        pdf_bytes = make_pdf_bytes()

        with patch("yazot.pdf_utils.PdfReader") as mock_reader_cls:
            pages = []
            for i in range(3):
                page = MagicMock()
                page.extract_text.return_value = f"Page {i + 1} text"
                pages.append(page)
            mock_reader = MagicMock()
            mock_reader.pages = pages
            mock_reader_cls.return_value = mock_reader

            text = resolver.extract_text(pdf_bytes)

        assert text == "Page 1 text\n\nPage 2 text\n\nPage 3 text"

    async def test_aclose_closes_all_sources(self) -> None:
        s1 = make_mock_source("a")
        s2 = make_mock_source("b")
        resolver = FulltextResolver([s1, s2])

        with patch.object(resolver._http, "aclose", new_callable=AsyncMock) as mock_http:
            await resolver.aclose()

        mock_http.assert_called_once()
        s1.aclose.assert_called_once()
        s2.aclose.assert_called_once()

    async def test_aclose_continues_on_source_error(self) -> None:
        """One broken source.aclose() must not prevent closing the rest."""
        s1 = make_mock_source("broken")
        s1.aclose = AsyncMock(side_effect=RuntimeError("close failed"))
        s2 = make_mock_source("ok")
        resolver = FulltextResolver([s1, s2])

        with patch.object(resolver._http, "aclose", new_callable=AsyncMock):
            await resolver.aclose()

        s1.aclose.assert_called_once()
        s2.aclose.assert_called_once()
