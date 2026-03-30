"""Tests for Crossref API — real HTTP calls."""

import pytest

from yazot.crossref_client import CrossrefClient, CrossrefWork
from yazot.exceptions import DOINotFoundError, InvalidDOIError


class TestCrossrefApi:
    """Tests that hit the real Crossref API."""

    @pytest.mark.asyncio
    async def test_get_metadata_valid_doi(self) -> None:
        """Test fetching metadata for a valid DOI."""
        doi = "10.1038/nature12373"

        client = CrossrefClient()
        metadata = await client.get_metadata_by_doi(doi)

        assert metadata is not None
        assert isinstance(metadata, CrossrefWork)
        assert doi == metadata.DOI
        assert len(metadata.title) > 0
        assert len(metadata.author) > 0

    @pytest.mark.asyncio
    async def test_get_metadata_with_url_prefix(self) -> None:
        """Test that DOI URL prefixes are correctly stripped."""
        doi = "https://doi.org/10.1038/nature12373"

        client = CrossrefClient()
        metadata = await client.get_metadata_by_doi(doi)

        assert metadata is not None
        assert isinstance(metadata, CrossrefWork)
        assert metadata.DOI == "10.1038/nature12373"

    @pytest.mark.asyncio
    async def test_get_metadata_invalid_doi_format(self) -> None:
        """Test that invalid DOI format raises error."""
        invalid_doi = "not-a-valid-doi"

        client = CrossrefClient()
        with pytest.raises(InvalidDOIError):
            await client.get_metadata_by_doi(invalid_doi)

    @pytest.mark.asyncio
    async def test_get_metadata_nonexistent_doi(self) -> None:
        """Test that non-existent DOI raises not found error."""
        nonexistent_doi = "10.9999/nonexistent.doi.99999"

        client = CrossrefClient()
        with pytest.raises(DOINotFoundError):
            await client.get_metadata_by_doi(nonexistent_doi)
