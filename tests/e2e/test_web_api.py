"""End-to-end write tests against real web API."""

import contextlib
import os
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.e2e.conftest import parse_tool_result, parse_tool_result_dict, parse_tool_result_list
from yazot.mcp_server import mcp
from yazot.models import Note, SearchCollectionResponse, ZoteroItem
from yazot.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.e2e.test_helpers import ZoteroTestDataManager


def _skip_without_web_credentials() -> None:
    if not os.getenv("TEST_ZOTERO_LIBRARY_ID") or not os.getenv("TEST_ZOTERO_API_KEY"):
        pytest.skip("Web API credentials not available")


class TestWebApiWrite:
    """End-to-end write tests that exercise the Zotero web API via MCP tools."""

    async def test_create_and_search_items(
        self,
        test_zotero_client: ZoteroClient,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Items created via test_data_manager are discoverable through search_articles."""
        _skip_without_web_credentials()

        items = await test_data_manager.create_test_items(count=3, template_type="journalArticle")
        assert len(items) == 3

        title_fragment = items[0].data.title.split()[0]

        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_articles",
                arguments={"query": title_fragment},
            )
            response = parse_tool_result(result, SearchCollectionResponse)

        assert isinstance(response.items, list)
        assert response.count >= 0
        found_keys = {item.key for item in response.items}
        assert items[0].key in found_keys

    async def test_create_collection_and_get_items(
        self,
        test_zotero_client: ZoteroClient,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Items placed in a collection are returned by get_collection_items."""
        _skip_without_web_credentials()

        collection_keys = await test_data_manager.create_test_collections(
            1, name_prefix="Live Write Test"
        )
        collection_key = collection_keys[0]

        items = await test_data_manager.create_test_items(count=5, collection_key=collection_key)
        assert len(items) == 5

        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_collection_items",
                arguments={"collection_key": collection_key},
            )
            response = parse_tool_result(result, SearchCollectionResponse)

        assert response.count == 5
        assert isinstance(response.items, list)

        returned_keys = {item.key for item in response.items}
        for item in items:
            assert item.key in returned_keys

    async def test_create_note_and_retrieve(
        self,
        test_zotero_client: ZoteroClient,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """A note created via create_note_for_item appears in get_item_notes output."""
        _skip_without_web_credentials()

        items = await test_data_manager.create_test_items(count=1, template_type="journalArticle")
        item_key = items[0].key

        async with Client(mcp) as client:
            note_result = await client.call_tool(
                "create_note_for_item",
                arguments={
                    "item_key": item_key,
                    "title": "Integration Test Note",
                    "content": "Content for live integration test.",
                },
            )
            note = parse_tool_result(note_result, Note)

        assert note.key
        assert note.parent_key == item_key

        async with Client(mcp) as client:
            notes_result = await client.call_tool(
                "get_item_notes",
                arguments={"item_key": item_key},
            )
            notes = parse_tool_result_list(notes_result, Note)

        note_keys = [n.key for n in notes]
        assert note.key in note_keys

    async def test_create_collection_hierarchy(
        self,
        test_zotero_client: ZoteroClient,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Items in a subcollection appear when get_collection_items is called with
        include_subcollections=True on the parent collection.
        """
        _skip_without_web_credentials()

        parent_key: str | None = None
        sub_key: str | None = None

        try:
            async with Client(mcp) as client:
                parent_result = await client.call_tool(
                    "create_collection",
                    arguments={"name": "Live Hierarchy Parent"},
                )
                parent_data = parse_tool_result_dict(parent_result)
                assert parent_data["key"]
                parent_key = parent_data["key"]

            async with Client(mcp) as client:
                sub_result = await client.call_tool(
                    "create_collection",
                    arguments={
                        "name": "Live Hierarchy Sub",
                        "parent_collection_key": parent_key,
                    },
                )
                sub_data = parse_tool_result_dict(sub_result)
                assert sub_data["key"]
                sub_key = sub_data["key"]

            sub_items = await test_data_manager.create_test_items(count=3, collection_key=sub_key)
            assert len(sub_items) == 3

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "get_collection_items",
                    arguments={
                        "collection_key": parent_key,
                        "include_subcollections": True,
                    },
                )
                response = parse_tool_result(result, SearchCollectionResponse)

            assert isinstance(response.items, list)
            returned_keys = {item.key for item in response.items}
            for item in sub_items:
                assert item.key in returned_keys

        finally:
            if sub_key is not None:
                with contextlib.suppress(Exception):
                    await test_zotero_client.delete_collection_by_key(sub_key)
            if parent_key is not None:
                with contextlib.suppress(Exception):
                    await test_zotero_client.delete_collection_by_key(parent_key)

    async def test_search_with_item_type_filter(
        self,
        test_zotero_client: ZoteroClient,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """search_articles with item_type filter only returns items of that type."""
        _skip_without_web_credentials()

        await test_data_manager.create_test_items(count=3, template_type="journalArticle")

        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_articles",
                arguments={"item_type": "journalArticle"},
            )
            response = parse_tool_result(result, SearchCollectionResponse)

        assert isinstance(response.items, list)
        for item in response.items:
            assert item.data.item_type == "journalArticle"


_DOI = "10.1038/nature12373"


class TestDoiSearchAndCreate:
    """End-to-end tests for the add_item_by_doi MCP tool."""

    async def test_add_by_doi_returns_item(
        self,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """add_item_by_doi creates an item with the expected key, title, DOI and creators."""
        _skip_without_web_credentials()

        item = None
        try:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": _DOI},
                )
                item = parse_tool_result(result, ZoteroItem)

            assert item.key
            assert item.data.title
            assert item.data.doi == _DOI
            assert len(item.data.creators) > 0

        finally:
            if item is not None:
                with contextlib.suppress(Exception):
                    await test_zotero_client.delete_item_by_key(item.key)

    async def test_add_by_doi_to_collection(
        self,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """An item added by DOI with collection_key appears in that collection."""
        _skip_without_web_credentials()

        collection_key: str | None = None
        item_key: str | None = None

        try:
            async with Client(mcp) as client:
                coll_result = await client.call_tool(
                    "create_collection",
                    arguments={"name": "DOI Test Collection"},
                )
                collection_data = parse_tool_result_dict(coll_result)
                assert collection_data["key"]
                collection_key = collection_data["key"]

                item_result = await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": _DOI, "collection_key": collection_key},
                )
                item = parse_tool_result(item_result, ZoteroItem)
                item_key = item.key

            assert collection_key in item.data.collections

        finally:
            if item_key is not None:
                with contextlib.suppress(Exception):
                    await test_zotero_client.delete_item_by_key(item_key)
            if collection_key is not None:
                with contextlib.suppress(Exception):
                    await test_zotero_client.delete_collection_by_key(collection_key)

    async def test_add_by_doi_with_tags(
        self,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Tags supplied to add_item_by_doi are present on the created item."""
        _skip_without_web_credentials()

        tags = ["test-tag-1", "test-tag-2"]
        item = None

        try:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": _DOI, "tags": tags},
                )
                item = parse_tool_result(result, ZoteroItem)

            item_tag_names = [t.tag for t in item.data.tags]
            for tag in tags:
                assert tag in item_tag_names

        finally:
            if item is not None:
                with contextlib.suppress(Exception):
                    await test_zotero_client.delete_item_by_key(item.key)

    async def test_doi_item_searchable(
        self,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """An item added by DOI is subsequently findable via search_articles."""
        _skip_without_web_credentials()

        item = None

        try:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": _DOI},
                )
                item = parse_tool_result(result, ZoteroItem)

            async with Client(mcp) as client:
                search_result = await client.call_tool(
                    "search_articles",
                    arguments={"query": "Nanometre-scale thermometry"},
                )
                response = parse_tool_result(search_result, SearchCollectionResponse)

            assert isinstance(response.items, list)
            found_keys = {i.key for i in response.items}
            assert item.key in found_keys

        finally:
            if item is not None:
                with contextlib.suppress(Exception):
                    await test_zotero_client.delete_item_by_key(item.key)

    async def test_invalid_doi_raises_error(
        self,
        test_zotero_client: ZoteroClient,
    ) -> None:
        """Calling add_item_by_doi with a syntactically invalid DOI raises an error."""
        _skip_without_web_credentials()

        async with Client(mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": "not-a-doi"},
                )
