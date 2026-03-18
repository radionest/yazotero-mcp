"""E2E tests for DOI-based item creation."""

import pytest
from fastmcp import Client

from src.crossref_client import CrossrefClient, CrossrefWork
from src.exceptions import DOINotFoundError, InvalidDOIError, ZoteroNotFoundError
from src.mcp_server import mcp
from src.models import ItemCreate
from src.zotero_client import ZoteroClient
from tests.test_helpers import ZoteroTestDataManager


class TestCrossrefClient:
    """Unit tests for Crossref API client."""

    @pytest.mark.asyncio
    async def test_get_metadata_valid_doi(self) -> None:
        """Test fetching metadata for a valid DOI."""
        # Using a well-known, stable DOI
        doi = "10.1038/nature12373"

        client = CrossrefClient()
        metadata = await client.get_metadata_by_doi(doi)

        # Verify basic metadata structure - now returns CrossrefWork
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
        # Use a syntactically valid but non-existent DOI
        nonexistent_doi = "10.9999/nonexistent.doi.99999"

        client = CrossrefClient()
        with pytest.raises(DOINotFoundError):
            await client.get_metadata_by_doi(nonexistent_doi)

    def test_crossref_to_zotero_journal_article(self) -> None:
        """Test conversion of journal article metadata."""
        # Sample Crossref metadata - now use Pydantic model
        crossref_data = CrossrefWork(
            type="journal-article",
            DOI="10.1234/example",
            title=["Test Article Title"],
            author=[
                {"given": "John", "family": "Doe"},
                {"given": "Jane", "family": "Smith"},
            ],
            **{
                "container-title": ["Nature"],
                "volume": "500",
                "issue": "7462",
                "page": "123-456",
                "ISSN": ["0028-0836"],
                "published-print": {"date-parts": [[2023, 8, 15]]},
                "abstract": "This is a test abstract.",
            },
        )

        client = CrossrefClient()
        zotero_item = client.crossref_to_zotero(crossref_data)

        # Verify conversion - now returns ItemCreate Pydantic model
        assert isinstance(zotero_item, ItemCreate)
        assert zotero_item.item_type == "journalArticle"

        # Convert to dict for detailed assertions
        item_dict = zotero_item.model_dump(by_alias=True, exclude_none=True)
        assert item_dict["itemType"] == "journalArticle"
        assert item_dict["title"] == "Test Article Title"
        assert item_dict["DOI"] == "10.1234/example"
        assert len(item_dict["creators"]) == 2
        assert item_dict["creators"][0]["firstName"] == "John"
        assert item_dict["creators"][0]["lastName"] == "Doe"
        assert item_dict["publicationTitle"] == "Nature"
        assert item_dict["volume"] == "500"
        assert item_dict["issue"] == "7462"
        assert item_dict["pages"] == "123-456"
        assert item_dict["ISSN"] == "0028-0836"
        assert item_dict["date"] == "2023-08-15"
        assert item_dict["abstractNote"] == "This is a test abstract."


class TestAddItemByDOI:
    """End-to-end tests for add_item_by_doi endpoint."""

    @pytest.mark.asyncio
    async def test_add_item_by_doi_simple(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test adding an item using a valid DOI."""
        # Using a well-known, stable DOI
        doi = "10.1038/nature12373"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "add_item_by_doi",
                arguments={"doi": doi},
            )
            item = result.data

        # Verify item was created
        assert item is not None
        assert item.key
        assert item.data.title
        assert doi == item.data.DOI
        assert len(item.data.creators) > 0

        # Clean up: delete the created item
        await test_zotero_client.delete_item_by_key(item.key)

    @pytest.mark.asyncio
    async def test_add_item_by_doi_with_tags(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test adding an item with tags."""
        doi = "10.1038/nature12373"
        tags = ["important", "to-read", "genetics"]

        async with Client(mcp) as client:
            result = await client.call_tool(
                "add_item_by_doi",
                arguments={"doi": doi, "tags": tags},
            )
            item = result.data

        # Verify item was created with tags
        assert item is not None
        assert item.key
        item_tags = [tag.tag for tag in item.data.tags]
        for tag in tags:
            assert tag in item_tags

        # Clean up
        await test_zotero_client.delete_item_by_key(item.key)

    @pytest.mark.asyncio
    async def test_add_item_by_doi_to_collection(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test adding an item to a specific collection."""
        # First create a test collection
        async with Client(mcp) as client:
            coll_result = await client.call_tool(
                "create_collection",
                arguments={"name": "Test DOI Collection"},
            )
            collection_data = coll_result.data

        # Add item to collection
        doi = "10.1038/nature12373"
        async with Client(mcp) as client:
            item_result = await client.call_tool(
                "add_item_by_doi",
                arguments={
                    "doi": doi,
                    "collection_key": collection_data["key"],
                },
            )
            item = item_result.data

        # Verify item was added to collection
        assert item is not None
        assert collection_data["key"] in item.data.collections

        # Clean up: delete item and collection
        await test_zotero_client.delete_item_by_key(item.key)
        await test_zotero_client.delete_collection_by_key(collection_data["key"])

    @pytest.mark.asyncio
    async def test_add_item_by_doi_with_url_format(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that DOI URLs are properly handled."""
        doi_url = "https://doi.org/10.1038/nature12373"

        async with Client(mcp) as client:
            result = await client.call_tool(
                "add_item_by_doi",
                arguments={"doi": doi_url},
            )
            item = result.data

        # Verify item was created with clean DOI
        assert item is not None
        assert item.data.DOI == "10.1038/nature12373"

        # Clean up
        await test_zotero_client.delete_item_by_key(item.key)

    @pytest.mark.asyncio
    async def test_add_item_by_invalid_doi(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Test that invalid DOI raises appropriate error."""
        invalid_doi = "not-a-valid-doi"

        async with Client(mcp) as client:
            with pytest.raises(ZoteroNotFoundError):  # Should raise ZoteroNotFoundError
                await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": invalid_doi},
                )
