"""E2E tests for DOI-based item creation."""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.e2e.conftest import parse_tool_result, parse_tool_result_dict
from tests.e2e.test_helpers import ZoteroTestDataManager
from yazot.models import ZoteroItem
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
        item = parse_tool_result(result, ZoteroItem)

        assert item is not None
        assert item.key
        assert item.data.title
        assert doi == item.data.doi
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
        item = parse_tool_result(result, ZoteroItem)

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
        collection_data = parse_tool_result_dict(coll_result)

        doi = "10.1038/nature12373"
        item_result = await mcp_client.call_tool(
            "add_item_by_doi",
            arguments={
                "doi": doi,
                "collection_key": collection_data["key"],
            },
        )
        item = parse_tool_result(item_result, ZoteroItem)

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
        item = parse_tool_result(result, ZoteroItem)

        assert item is not None
        assert item.data.doi == "10.1038/nature12373"

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
