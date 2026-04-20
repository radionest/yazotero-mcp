"""External fulltext resolver — cascading PDF retrieval from open-access sources."""

import logging
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from .exceptions import FulltextDownloadError, FulltextNotFoundError, FulltextSourceError
from .fulltext_source import FulltextSource
from .pdf_utils import extract_text_from_pdf

logger = logging.getLogger(__name__)


# --- Pydantic models for API responses ---


class UnpaywallOALocation(BaseModel):
    url_for_pdf: str | None = None
    url: str | None = None
    is_best: bool = False

    model_config = {"populate_by_name": True, "extra": "allow"}


class UnpaywallWork(BaseModel):
    doi: str
    is_oa: bool
    best_oa_location: UnpaywallOALocation | None = None
    oa_locations: list[UnpaywallOALocation] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "allow"}


class CoreWork(BaseModel):
    id: int | str
    doi: str | None = None
    download_url: str | None = Field(None, alias="downloadUrl")
    full_text: str | None = Field(None, alias="fullText")
    title: str | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class CoreSearchResponse(BaseModel):
    total_hits: int = Field(0, alias="totalHits")
    results: list[CoreWork] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "allow"}


# --- Built-in sources ---


class UnpaywallClient:
    """Client for Unpaywall open-access PDF discovery."""

    BASE_URL = "https://api.unpaywall.org/v2"
    TIMEOUT = 30

    def __init__(self, email: str) -> None:
        self.email = email
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)

    @property
    def name(self) -> str:
        return "unpaywall"

    @property
    def description(self) -> str:
        return "Unpaywall — legal open-access PDF discovery by DOI"

    async def find_pdf_url(self, *, doi: str | None = None, title: str | None = None) -> str | None:
        """Find open-access PDF URL for a DOI via Unpaywall."""
        if not doi:
            return None
        url = f"{self.BASE_URL}/{quote(doi, safe='')}"
        try:
            response = await self.client.get(url, params={"email": self.email})
            if response.status_code == 404:
                return None
            response.raise_for_status()
            work = UnpaywallWork.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            raise FulltextSourceError("Unpaywall", f"HTTP {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise FulltextSourceError("Unpaywall", str(e)) from e

        # Try best OA location first, then all locations
        if work.best_oa_location and work.best_oa_location.url_for_pdf:
            return work.best_oa_location.url_for_pdf
        for loc in work.oa_locations:
            if loc.url_for_pdf:
                return loc.url_for_pdf
        return None

    async def aclose(self) -> None:
        await self.client.aclose()


class CoreClient:
    """Client for CORE academic fulltext search."""

    BASE_URL = "https://api.core.ac.uk/v3"
    TIMEOUT = 30

    def __init__(self, api_key: str) -> None:
        self.client = httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @property
    def name(self) -> str:
        return "core"

    @property
    def description(self) -> str:
        return "CORE — academic fulltext aggregator, search by DOI or title"

    async def find_pdf_url(self, *, doi: str | None = None, title: str | None = None) -> str | None:
        """Search CORE for a PDF download URL."""
        query = f'doi:"{doi}"' if doi else title
        if not query:
            return None

        url = f"{self.BASE_URL}/search/works"
        try:
            response = await self.client.get(url, params={"q": query, "limit": 5})
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = CoreSearchResponse.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            raise FulltextSourceError("CORE", f"HTTP {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise FulltextSourceError("CORE", str(e)) from e

        for work in data.results:
            if work.download_url:
                return work.download_url
        return None

    async def aclose(self) -> None:
        await self.client.aclose()


# --- Cascade Resolver ---


class FulltextResolver:
    """Cascading resolver: iterates over sources in order until one returns a PDF URL."""

    def __init__(self, sources: list[FulltextSource]) -> None:
        self._sources = sources
        self._http = httpx.AsyncClient(timeout=60, follow_redirects=True)

    @property
    def is_configured(self) -> bool:
        return len(self._sources) > 0

    @property
    def sources(self) -> list[FulltextSource]:
        return list(self._sources)

    async def resolve(self, doi: str | None, title: str | None) -> tuple[str, str]:
        """Find PDF URL through cascade. Returns (pdf_url, source_name)."""
        if doi is not None:
            doi = doi.strip() or None
        if title is not None:
            title = title.strip() or None

        if doi is None and title is None:
            raise FulltextNotFoundError(doi=doi, title=title)

        for source in self._sources:
            try:
                if doi is not None:
                    url = await source.find_pdf_url(doi=doi, title=title)
                else:
                    # title is guaranteed non-None by the early guard above
                    url = await source.find_pdf_url(title=title)  # type: ignore[arg-type]
                if url:
                    return url, source.name
            except FulltextSourceError as e:
                logger.warning("%s failed: %s", source.name, e)
            except Exception:
                logger.warning(
                    "Unexpected failure from fulltext source %s",
                    source.name,
                    exc_info=True,
                )

        raise FulltextNotFoundError(doi=doi, title=title)

    async def download(self, pdf_url: str) -> bytes:
        """Download PDF bytes from URL."""
        try:
            response = await self._http.get(pdf_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise FulltextDownloadError(pdf_url, f"HTTP {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise FulltextDownloadError(pdf_url, str(e)) from e

        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            raise FulltextDownloadError(pdf_url, f"Unexpected content-type: {content_type}")

        if not response.content:
            raise FulltextDownloadError(pdf_url, "Empty response body")

        return response.content

    def extract_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using pypdf."""
        try:
            return extract_text_from_pdf(pdf_bytes)
        except ValueError as e:
            raise FulltextDownloadError("pdf", str(e)) from e

    async def aclose(self) -> None:
        try:
            await self._http.aclose()
        finally:
            for source in self._sources:
                try:
                    await source.aclose()
                except Exception:
                    logger.warning(
                        "Failed to close fulltext source %s",
                        source.name,
                        exc_info=True,
                    )
