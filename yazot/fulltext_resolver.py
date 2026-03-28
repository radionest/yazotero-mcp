"""External fulltext resolver — cascading PDF retrieval from open-access sources."""

import logging
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from .config import Settings
from .exceptions import FulltextDownloadError, FulltextNotFoundError, FulltextSourceError
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


# --- API Clients ---


class UnpaywallClient:
    """Client for Unpaywall open-access PDF discovery."""

    BASE_URL = "https://api.unpaywall.org/v2"
    TIMEOUT = 30

    def __init__(self, email: str) -> None:
        self.email = email
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)

    async def find_pdf_url(self, doi: str) -> str | None:
        """Find open-access PDF URL for a DOI via Unpaywall."""
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

    async def find_pdf_url(self, doi: str | None, title: str | None) -> str | None:
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


class LibgenClient:
    """Client for Library Genesis article search (gray zone)."""

    TIMEOUT = 45

    def __init__(self, mirror: str) -> None:
        self.mirror = mirror.rstrip("/")
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True)

    async def find_pdf_url(self, title: str) -> str | None:
        """Search Libgen Sci-Tech for article PDF URL by title."""
        search_url = f"{self.mirror}/search.php"
        try:
            response = await self.client.get(
                search_url,
                params={"req": title, "res": "25", "column": "title"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise FulltextSourceError("Libgen", f"HTTP {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise FulltextSourceError("Libgen", str(e)) from e

        soup = BeautifulSoup(response.text, "html.parser")
        # Libgen search results table contains MD5 links
        for link in soup.select("table.c a[href*='md5=']"):
            href = link.get("href", "")
            if isinstance(href, str) and "md5=" in href:
                # Extract MD5 and build direct download URL
                md5_start = href.index("md5=") + 4
                md5 = href[md5_start:md5_start + 32]
                if len(md5) == 32:
                    return f"{self.mirror}/get.php?md5={md5}"
        return None

    async def aclose(self) -> None:
        await self.client.aclose()


# --- Cascade Resolver ---


class FulltextResolver:
    """Cascading resolver: Unpaywall → CORE → Libgen (if enabled)."""

    def __init__(self, settings: Settings) -> None:
        self._unpaywall = (
            UnpaywallClient(settings.unpaywall_email) if settings.unpaywall_email else None
        )
        self._core = CoreClient(settings.core_api_key) if settings.core_api_key else None
        self._libgen = (
            LibgenClient(settings.fulltext_libgen_mirror)
            if settings.fulltext_libgen_enabled
            else None
        )
        self._http = httpx.AsyncClient(timeout=60, follow_redirects=True)

    @property
    def is_configured(self) -> bool:
        return any([self._unpaywall, self._core, self._libgen])

    async def resolve(self, doi: str | None, title: str | None) -> tuple[str, str]:
        """Find PDF URL through cascade. Returns (pdf_url, source_name)."""
        if doi and self._unpaywall:
            try:
                url = await self._unpaywall.find_pdf_url(doi)
                if url:
                    return url, "unpaywall"
            except FulltextSourceError as e:
                logger.warning("Unpaywall failed for %s: %s", doi, e)

        if self._core and (doi or title):
            try:
                url = await self._core.find_pdf_url(doi, title)
                if url:
                    return url, "core"
            except FulltextSourceError as e:
                logger.warning("CORE failed for doi=%s title=%s: %s", doi, title, e)

        if title and self._libgen:
            try:
                url = await self._libgen.find_pdf_url(title)
                if url:
                    return url, "libgen"
            except FulltextSourceError as e:
                logger.warning("Libgen failed for %s: %s", title, e)

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
        await self._http.aclose()
        if self._unpaywall:
            await self._unpaywall.aclose()
        if self._core:
            await self._core.aclose()
        if self._libgen:
            await self._libgen.aclose()
