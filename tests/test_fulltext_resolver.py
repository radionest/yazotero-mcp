"""Tests for external fulltext resolver — Unpaywall, CORE, Libgen clients + cascade."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pypdf import PdfWriter

from tests.conftest import make_httpx_response
from yazot.config import Settings
from yazot.exceptions import (
    FulltextDownloadError,
    FulltextNotFoundError,
    FulltextSourceError,
)
from yazot.fulltext_resolver import (
    CoreClient,
    FulltextResolver,
    LibgenClient,
    UnpaywallClient,
)

# --- Helpers ---


def make_pdf_bytes() -> bytes:
    """Create minimal valid PDF bytes for testing."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# --- UnpaywallClient tests ---


class TestUnpaywallClient:
    @pytest.fixture
    def client(self) -> UnpaywallClient:
        return UnpaywallClient(email="test@example.com")

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
            url = await client.find_pdf_url("10.1234/test")

        assert url == "https://example.com/paper.pdf"

    async def test_find_pdf_url_fallback_to_oa_locations(
        self, client: UnpaywallClient
    ) -> None:
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
            url = await client.find_pdf_url("10.1234/test")

        assert url == "https://archive.org/paper.pdf"

    async def test_find_pdf_url_not_found(self, client: UnpaywallClient) -> None:
        mock_response = make_httpx_response(status_code=404)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url("10.1234/nonexistent")

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
            url = await client.find_pdf_url("10.1234/closed")

        assert url is None

    async def test_find_pdf_url_server_error(self, client: UnpaywallClient) -> None:
        mock_response = make_httpx_response(status_code=500)

        with (
            patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextSourceError, match="Unpaywall"),
        ):
            await client.find_pdf_url("10.1234/test")


# --- CoreClient tests ---


class TestCoreClient:
    @pytest.fixture
    def client(self) -> CoreClient:
        return CoreClient(api_key="test-key")

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
            url = await client.find_pdf_url("10.1234/test", None)

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
            url = await client.find_pdf_url(None, "Machine Learning Paper")

        assert url == "https://core.ac.uk/download/pdf/67890.pdf"

    async def test_find_pdf_url_no_results(self, client: CoreClient) -> None:
        response_data = {"totalHits": 0, "results": []}
        mock_response = make_httpx_response(json_data=response_data)

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url("10.1234/nothing", None)

        assert url is None

    async def test_find_pdf_url_no_query(self, client: CoreClient) -> None:
        url = await client.find_pdf_url(None, None)
        assert url is None

    async def test_find_pdf_url_server_error(self, client: CoreClient) -> None:
        mock_response = make_httpx_response(status_code=500)

        with (
            patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextSourceError, match="CORE"),
        ):
            await client.find_pdf_url("10.1234/test", None)


# --- LibgenClient tests ---


class TestLibgenClient:
    @pytest.fixture
    def client(self) -> LibgenClient:
        return LibgenClient(mirror="https://libgen.is")

    async def test_find_pdf_url_success(self, client: LibgenClient) -> None:
        html = """
        <html><body>
        <table class="c">
            <tr><td><a href="/book/index.php?md5=d41d8cd98f00b204e9800998ecf8427e">Title</a></td></tr>
        </table>
        </body></html>
        """
        mock_response = make_httpx_response(
            content=html.encode(),
            headers={"content-type": "text/html"},
        )
        # Override json to return text
        mock_response._content = html.encode()

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url("Test Article Title")

        assert url == "https://libgen.is/get.php?md5=d41d8cd98f00b204e9800998ecf8427e"

    async def test_find_pdf_url_no_results(self, client: LibgenClient) -> None:
        html = "<html><body><table class='c'></table></body></html>"
        mock_response = make_httpx_response(content=html.encode())

        with patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response):
            url = await client.find_pdf_url("Nonexistent Article")

        assert url is None

    async def test_find_pdf_url_server_error(self, client: LibgenClient) -> None:
        mock_response = make_httpx_response(status_code=503)

        with (
            patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(FulltextSourceError, match="Libgen"),
        ):
            await client.find_pdf_url("Test")


# --- FulltextResolver tests ---


class TestFulltextResolver:
    @pytest.fixture
    def settings_all(self) -> Settings:
        return Settings(
            zotero_local=True,
            unpaywall_email="test@example.com",
            core_api_key="test-core-key",
            fulltext_libgen_enabled=True,
            fulltext_libgen_mirror="https://libgen.is",
        )

    @pytest.fixture
    def settings_unpaywall_only(self) -> Settings:
        return Settings(
            zotero_local=True,
            unpaywall_email="test@example.com",
        )

    @pytest.fixture
    def settings_none(self) -> Settings:
        return Settings(zotero_local=True)

    def test_is_configured_all(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        assert resolver.is_configured is True

    def test_is_configured_none(self, settings_none: Settings) -> None:
        resolver = FulltextResolver(settings_none)
        assert resolver.is_configured is False

    def test_libgen_not_created_when_disabled(self, settings_unpaywall_only: Settings) -> None:
        resolver = FulltextResolver(settings_unpaywall_only)
        assert resolver._libgen is None
        assert resolver._unpaywall is not None
        assert resolver._core is None

    async def test_cascade_unpaywall_succeeds(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        assert resolver._unpaywall is not None
        with patch.object(
            resolver._unpaywall, "find_pdf_url", new_callable=AsyncMock, return_value="https://pdf.com/a.pdf"
        ):
            url, source = await resolver.resolve("10.1234/test", "Test Title")

        assert url == "https://pdf.com/a.pdf"
        assert source == "unpaywall"

    async def test_cascade_fallback_to_core(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        assert resolver._unpaywall is not None
        assert resolver._core is not None
        with (
            patch.object(
                resolver._unpaywall, "find_pdf_url", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                resolver._core, "find_pdf_url", new_callable=AsyncMock, return_value="https://core.ac.uk/pdf.pdf"
            ),
        ):
            url, source = await resolver.resolve("10.1234/test", "Test Title")

        assert url == "https://core.ac.uk/pdf.pdf"
        assert source == "core"

    async def test_cascade_fallback_to_libgen(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        assert resolver._unpaywall is not None
        assert resolver._core is not None
        assert resolver._libgen is not None
        with (
            patch.object(
                resolver._unpaywall, "find_pdf_url", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                resolver._core, "find_pdf_url", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                resolver._libgen, "find_pdf_url", new_callable=AsyncMock, return_value="https://libgen.is/get.php?md5=abc"
            ),
        ):
            url, source = await resolver.resolve("10.1234/test", "Test Title")

        assert url == "https://libgen.is/get.php?md5=abc"
        assert source == "libgen"

    async def test_cascade_all_fail(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        assert resolver._unpaywall is not None
        assert resolver._core is not None
        assert resolver._libgen is not None
        with (
            patch.object(
                resolver._unpaywall, "find_pdf_url", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                resolver._core, "find_pdf_url", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                resolver._libgen, "find_pdf_url", new_callable=AsyncMock, return_value=None
            ),
            pytest.raises(FulltextNotFoundError),
        ):
            await resolver.resolve("10.1234/test", "Test Title")

    async def test_cascade_error_continues(self, settings_all: Settings) -> None:
        """Source errors are non-fatal — cascade continues."""
        resolver = FulltextResolver(settings_all)
        assert resolver._unpaywall is not None
        assert resolver._core is not None
        with (
            patch.object(
                resolver._unpaywall,
                "find_pdf_url",
                new_callable=AsyncMock,
                side_effect=FulltextSourceError("Unpaywall", "timeout"),
            ),
            patch.object(
                resolver._core,
                "find_pdf_url",
                new_callable=AsyncMock,
                return_value="https://core.ac.uk/pdf.pdf",
            ),
        ):
            url, source = await resolver.resolve("10.1234/test", "Test Title")

        assert source == "core"

    async def test_cascade_no_doi_skips_unpaywall(
        self, settings_all: Settings
    ) -> None:
        resolver = FulltextResolver(settings_all)
        assert resolver._core is not None
        with patch.object(
            resolver._core,
            "find_pdf_url",
            new_callable=AsyncMock,
            return_value="https://core.ac.uk/pdf.pdf",
        ) as mock_core:
            url, source = await resolver.resolve(None, "Test Title")

        assert source == "core"
        mock_core.assert_called_once_with(None, "Test Title")

    async def test_download_success(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
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

    async def test_download_wrong_content_type(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        mock_response = make_httpx_response(
            content=b"<html>Not a PDF</html>",
            headers={"content-type": "text/html"},
        )

        with (
            patch.object(
                resolver._http, "get", new_callable=AsyncMock, return_value=mock_response
            ),
            pytest.raises(FulltextDownloadError, match="content-type"),
        ):
            await resolver.download("https://example.com/not-a-pdf")

    async def test_download_empty_pdf_body(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        mock_response = make_httpx_response(
            content=b"",
            headers={"content-type": "application/pdf"},
        )

        with (
            patch.object(
                resolver._http, "get", new_callable=AsyncMock, return_value=mock_response
            ),
            pytest.raises(FulltextDownloadError, match="Empty response body"),
        ):
            await resolver.download("https://example.com/empty.pdf")

    async def test_download_http_error(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        mock_response = make_httpx_response(status_code=403)

        with (
            patch.object(
                resolver._http, "get", new_callable=AsyncMock, return_value=mock_response
            ),
            pytest.raises(FulltextDownloadError, match="HTTP 403"),
        ):
            await resolver.download("https://example.com/forbidden.pdf")

    def test_extract_text(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        pdf_bytes = make_pdf_bytes()

        with patch("yazot.pdf_utils.PdfReader") as mock_reader_cls:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Page 1 text"
            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_cls.return_value = mock_reader

            text = resolver.extract_text(pdf_bytes)

        assert text == "Page 1 text"

    def test_extract_text_pdf_parse_failure(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
        pdf_bytes = make_pdf_bytes()

        with (
            patch(
                "yazot.pdf_utils.PdfReader",
                side_effect=ValueError("corrupt"),
            ),
            pytest.raises(FulltextDownloadError, match="Failed to parse PDF"),
        ):
            resolver.extract_text(pdf_bytes)

    def test_extract_text_multiple_pages(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)
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

    async def test_aclose_closes_all_clients(self, settings_all: Settings) -> None:
        resolver = FulltextResolver(settings_all)

        with (
            patch.object(resolver._http, "aclose", new_callable=AsyncMock) as mock_http,
            patch.object(resolver._unpaywall, "aclose", new_callable=AsyncMock) as mock_unpaywall,
            patch.object(resolver._core, "aclose", new_callable=AsyncMock) as mock_core,
            patch.object(resolver._libgen, "aclose", new_callable=AsyncMock) as mock_libgen,
        ):
            await resolver.aclose()

        mock_http.assert_called_once()
        mock_unpaywall.assert_called_once()
        mock_core.assert_called_once()
        mock_libgen.assert_called_once()
