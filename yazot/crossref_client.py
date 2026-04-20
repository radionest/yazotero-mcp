"""Crossref API client for fetching bibliographic metadata."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from .exceptions import (
    CrossRefAPIError,
    CrossRefConnectionError,
    DOINotFoundError,
    InvalidDOIError,
)
from .models import ItemCreate

# Pydantic models for Crossref API response validation


class CrossrefDate(BaseModel):
    """Date object from Crossref API.

    Structure: {"date-parts": [[2023, 1, 15]]}
    """

    date_parts: list[list[int]] = Field(alias="date-parts", default_factory=list)

    model_config = {"populate_by_name": True}

    def format_date(self) -> str:
        """Format date as string (YYYY-MM-DD, YYYY-MM, or YYYY)."""
        if not self.date_parts or not self.date_parts[0]:
            return ""

        parts = self.date_parts[0]
        if len(parts) >= 3:
            return f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
        elif len(parts) == 2:
            return f"{parts[0]}-{parts[1]:02d}"
        elif len(parts) == 1:
            return str(parts[0])
        return ""


class CrossrefAuthor(BaseModel):
    """Author object from Crossref API."""

    given: str | None = None
    family: str | None = None
    sequence: str | None = None
    affiliation: list[dict[str, Any]] = Field(default_factory=list)
    ORCID: str | None = None
    authenticated_orcid: bool | None = Field(None, alias="authenticated-orcid")

    model_config = {"populate_by_name": True, "extra": "allow"}


class CrossrefLicense(BaseModel):
    """License object from Crossref API."""

    URL: str | None = None
    start: CrossrefDate | None = None
    delay_in_days: int | None = Field(None, alias="delay-in-days")
    content_version: str | None = Field(None, alias="content-version")

    model_config = {"populate_by_name": True, "extra": "allow"}


class CrossrefReference(BaseModel):
    """Reference object from Crossref API."""

    key: str | None = None
    doi: str | None = Field(None, alias="DOI")
    article_title: str | None = Field(None, alias="article-title")
    author: str | None = None
    year: str | None = None
    journal_title: str | None = Field(None, alias="journal-title")

    model_config = {"populate_by_name": True, "extra": "allow"}


class CrossrefWork(BaseModel):
    """Main Crossref work object with bibliographic metadata.

    Represents the 'message' field in Crossref API response.
    """

    # Core identifiers
    DOI: str
    type: str
    URL: str | None = None

    # Title and abstract
    title: list[str] = Field(default_factory=list)
    subtitle: list[str] = Field(default_factory=list)
    short_title: list[str] = Field(default_factory=list, alias="short-title")
    abstract: str | None = None

    # Publication info
    container_title: list[str] = Field(default_factory=list, alias="container-title")
    short_container_title: list[str] = Field(default_factory=list, alias="short-container-title")
    publisher: str | None = None

    # Volume/Issue/Pages
    volume: str | None = None
    issue: str | None = None
    page: str | None = None

    # Authors
    author: list[CrossrefAuthor] = Field(default_factory=list)

    # Identifiers
    ISSN: list[str] = Field(default_factory=list)
    ISBN: list[str] = Field(default_factory=list)

    # Dates
    created: CrossrefDate | None = None
    published_print: CrossrefDate | None = Field(None, alias="published-print")
    published_online: CrossrefDate | None = Field(None, alias="published-online")
    issued: CrossrefDate | None = None

    # Metadata
    language: str | None = None
    license: list[CrossrefLicense] = Field(default_factory=list)
    reference: list[CrossrefReference] = Field(default_factory=list)

    # Counts
    is_referenced_by_count: int | None = Field(None, alias="is-referenced-by-count")
    reference_count: int | None = Field(None, alias="reference-count")
    references_count: int | None = Field(None, alias="references-count")

    model_config = {"populate_by_name": True, "extra": "allow"}

    def get_title(self) -> str:
        """Get first title from title list."""
        return self.title[0] if self.title else ""

    def get_container_title(self) -> str:
        """Get first container title (journal/conference name)."""
        return self.container_title[0] if self.container_title else ""

    def get_issn(self) -> str:
        """Get first ISSN."""
        return self.ISSN[0] if self.ISSN else ""

    def get_isbn(self) -> str:
        """Get first ISBN."""
        return self.ISBN[0] if self.ISBN else ""


class CrossrefClient:
    """Client for interacting with Crossref API to fetch metadata by DOI."""

    BASE_URL = "https://api.crossref.org/works"
    TIMEOUT = 30

    def __init__(self) -> None:
        """Initialize Crossref client."""
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        await self.client.aclose()

    async def get_metadata_by_doi(self, doi: str) -> CrossrefWork:
        """Fetch bibliographic metadata from Crossref API using DOI.

        Args:
            doi: Digital Object Identifier (e.g., "10.1234/example")

        Returns:
            CrossrefWork object with validated metadata from Crossref

        Raises:
            InvalidDOIError: If DOI format is invalid
            DOINotFoundError: If DOI is not found in Crossref
            CrossRefAPIError: If API request fails
            CrossRefConnectionError: If connection fails
        """
        # Clean DOI: remove common prefixes and normalize to lowercase
        doi = doi.strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if doi.lower().startswith(prefix):
                doi = doi[len(prefix) :]
                break
        doi = doi.strip().lower()

        # Validate DOI format (must start with 10.)
        if not doi.startswith("10."):
            raise InvalidDOIError(doi, "DOI must start with '10.'")

        url = f"{self.BASE_URL}/{doi}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            # Crossref wraps metadata in "message" field
            if "message" not in data:
                raise CrossRefAPIError(doi, response.status_code, "Invalid response format")

            # Parse and validate response with Pydantic
            return CrossrefWork.model_validate(data["message"])

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise DOINotFoundError(doi) from e
            raise CrossRefAPIError(doi, e.response.status_code) from e
        except httpx.RequestError as e:
            raise CrossRefConnectionError(str(e)) from e

    def crossref_to_zotero(self, crossref_data: CrossrefWork) -> ItemCreate:
        """Convert Crossref metadata to Zotero item format.

        Args:
            crossref_data: CrossrefWork object from Crossref API

        Returns:
            ItemCreate Pydantic model, suitable for create_items API
        """
        # Determine item type
        item_type = self._map_crossref_type(crossref_data.type)

        # Build creators list (authors)
        creators = []
        for author in crossref_data.author:
            creator = {"creatorType": "author"}

            if author.given and author.family:
                creator["firstName"] = author.given
                creator["lastName"] = author.family
            elif author.family:
                creator["name"] = author.family
            elif author.given:
                creator["name"] = author.given
            else:
                continue

            creators.append(creator)

        # Build Zotero item
        zotero_item = {
            "itemType": item_type,
            "title": crossref_data.get_title(),
            "creators": creators,
            "abstractNote": crossref_data.abstract or "",
            "DOI": crossref_data.DOI,
            "url": crossref_data.URL or "",
            "date": crossref_data.created.format_date() if crossref_data.created else "",
        }

        # Add publication-specific fields
        if item_type == "journalArticle":
            zotero_item["publicationTitle"] = crossref_data.get_container_title()
            zotero_item["volume"] = crossref_data.volume or ""
            zotero_item["issue"] = crossref_data.issue or ""
            zotero_item["pages"] = crossref_data.page or ""
            zotero_item["ISSN"] = crossref_data.get_issn()

            # Publication date from published-print or published-online
            pub_date = (
                crossref_data.published_print
                or crossref_data.published_online
                or crossref_data.created
            )
            if pub_date:
                zotero_item["date"] = pub_date.format_date()

        elif item_type == "conferencePaper":
            zotero_item["proceedingsTitle"] = crossref_data.get_container_title()
            zotero_item["pages"] = crossref_data.page or ""

        elif item_type == "book":
            zotero_item["publisher"] = crossref_data.publisher or ""
            zotero_item["ISBN"] = crossref_data.get_isbn()

        # Remove empty fields and create Pydantic model
        clean_data = {k: v for k, v in zotero_item.items() if v}
        return ItemCreate(**clean_data)

    def _map_crossref_type(self, crossref_type: str) -> str:
        """Map Crossref type to Zotero item type."""
        type_mapping = {
            "journal-article": "journalArticle",
            "book-chapter": "bookSection",
            "book": "book",
            "proceedings-article": "conferencePaper",
            "report": "report",
            "dataset": "dataset",
            "posted-content": "preprint",
        }
        return type_mapping.get(crossref_type, "journalArticle")
