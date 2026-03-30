"""E2E tests for DOI-based item creation."""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.e2e.test_helpers import ZoteroTestDataManager
from yazot.zotero_client import ZoteroClient


class TestAddItemByDOI:
    """End-to-end tests for add_item_by_doi endpoint."""

    @pytest.mark.asyncio
    async def test_add_item_by_doi_simple(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
        mcp_client: Client,
    ) -> None:
        """Test adding an item using a valid DOI."""
        doi = "10.1038/nature12373"

        result = await mcp_client.call_tool(
            "add_item_by_doi",
            arguments={"doi": doi},
        )
        item = result.data

        assert item is not None
        assert item.key
        assert item.data.title
        assert doi == item.data.DOI
        assert len(item.data.creators) > 0

        await test_zotero_client.delete_item_by_key(item.key)

    @pytest.mark.asyncio
    async def test_add_item_by_doi_with_tags(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
        mcp_client: Client,
    ) -> None:
        """Test adding an item with tags."""
        doi = "10.1038/nature12373"
        tags = ["important", "to-read", "genetics"]

        result = await mcp_client.call_tool(
            "add_item_by_doi",
            arguments={"doi": doi, "tags": tags},
        )
        item = result.data

        assert item is not None
        assert item.key
        item_tags = [tag.tag for tag in item.data.tags]
        for tag in tags:
            assert tag in item_tags

        await test_zotero_client.delete_item_by_key(item.key)

    @pytest.mark.asyncio
    async def test_add_item_by_doi_to_collection(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
        mcp_client: Client,
    ) -> None:
        """Test adding an item to a specific collection."""
        coll_result = await mcp_client.call_tool(
            "create_collection",
            arguments={"name": "Test DOI Collection"},
        )
        collection_data = coll_result.data

        doi = "10.1038/nature12373"
        item_result = await mcp_client.call_tool(
            "add_item_by_doi",
            arguments={
                "doi": doi,
                "collection_key": collection_data["key"],
            },
        )
        item = item_result.data

        assert item is not None
        assert collection_data["key"] in item.data.collections

        await test_zotero_client.delete_item_by_key(item.key)
        await test_zotero_client.delete_collection_by_key(collection_data["key"])

    @pytest.mark.asyncio
    async def test_add_item_by_doi_with_url_format(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
        mcp_client: Client,
    ) -> None:
        """Test that DOI URLs are properly handled."""
        doi_url = "https://doi.org/10.1038/nature12373"

        result = await mcp_client.call_tool(
            "add_item_by_doi",
            arguments={"doi": doi_url},
        )
        item = result.data

        assert item is not None
        assert item.data.DOI == "10.1038/nature12373"

        await test_zotero_client.delete_item_by_key(item.key)

    @pytest.mark.asyncio
    async def test_add_item_by_invalid_doi(
        self,
        test_data_manager: ZoteroTestDataManager,
        test_zotero_client: ZoteroClient,
        mcp_client: Client,
    ) -> None:
        """Test that invalid DOI raises appropriate error."""
        invalid_doi = "not-a-valid-doi"

        with pytest.raises(ToolError, match="DOI must start with"):
            await mcp_client.call_tool(
                "add_item_by_doi",
                arguments={"doi": invalid_doi},
            )
