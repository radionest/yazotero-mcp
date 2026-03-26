"""Integration tests against live local Zotero instance and real web API."""

import contextlib
import os
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from yazot.mcp_server import mcp
from yazot.models import ZoteroSearchParams
from yazot.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.test_helpers import ZoteroTestDataManager
    from tests.zotero_instance import ZoteroInstance


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _skip_without_web_credentials() -> None:
    if not os.getenv("TEST_ZOTERO_LIBRARY_ID") or not os.getenv("TEST_ZOTERO_API_KEY"):
        pytest.skip("Web API credentials not available")


# ---------------------------------------------------------------------------
# Class 1: TestLocalInstanceRead
# ---------------------------------------------------------------------------


class TestLocalInstanceRead:
    """Tests that exercise ZoteroClient against a live local Zotero process.

    Every test skips when ZOTERO_TEST_INSTANCE is not enabled (fixture yields None).
    """

    def test_instance_health_check(
        self,
        zotero_test_environment: "ZoteroInstance | None",
    ) -> None:
        """Verify the provisioned Zotero process responds to HTTP health checks."""
        if zotero_test_environment is None:
            pytest.skip("Live Zotero instance not enabled")

        assert zotero_test_environment.health_check() is True

    def test_client_connects_with_custom_port(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """ZoteroClient created for the live instance uses local mode and correct port.

        NOTE: Accesses private _client.endpoint to verify port configuration.
        """
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        assert local_live_client.mode == "local"
        assert str(zotero_test_environment.port) in local_live_client._client.endpoint

    async def test_get_items_returns_list(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """get_items() against the live local instance returns a list."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        items = await local_live_client.get_items()
        assert isinstance(items, list)

    async def test_get_collections_returns_list(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """get_collections() against the live local instance returns a list."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        collections = await local_live_client.get_collections()
        assert isinstance(collections, list)

    async def test_search_items_returns_list(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
    ) -> None:
        """search_items() with empty params against live local instance returns a list."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        items = await local_live_client.search_items(ZoteroSearchParams())
        assert isinstance(items, list)

    async def test_mcp_search_via_local_instance(
        self,
        zotero_test_environment: "ZoteroInstance | None",
        local_live_client: ZoteroClient | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MCP search_articles tool works when env vars point to the live local instance."""
        if zotero_test_environment is None or local_live_client is None:
            pytest.skip("Live Zotero instance not enabled")

        port = zotero_test_environment.port
        monkeypatch.setenv("ZOTERO_LOCAL", "true")
        monkeypatch.setenv("ZOTERO_PORT", str(port))
        monkeypatch.setenv("ZOTERO_LIBRARY_ID", "0")
        monkeypatch.setenv("ZOTERO_API_KEY", "")

        async with Client(mcp) as client:
            result = await client.call_tool("search_articles", arguments={"search_params": {}})
            response = result.data

        assert isinstance(response.items, list)
        assert response.count >= 0


# ---------------------------------------------------------------------------
# Class 2: TestWebApiWrite
# ---------------------------------------------------------------------------


class TestWebApiWrite:
    """End-to-end write tests that exercise the Zotero web API via MCP tools.

    Every test skips when TEST_ZOTERO_LIBRARY_ID / TEST_ZOTERO_API_KEY are absent.
    """

    async def test_create_and_search_items(
        self,
        test_zotero_client: ZoteroClient,
        test_data_manager: "ZoteroTestDataManager",
    ) -> None:
        """Items created via test_data_manager are discoverable through search_articles."""
        _skip_without_web_credentials()

        items = await test_data_manager.create_test_items(count=3, template_type="journalArticle")
        assert len(items) == 3

        # Use the title fragment of the first item as the search query.
        title_fragment = items[0].data.title.split()[0]

        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_articles",
                arguments={"search_params": {"q": title_fragment}},
            )
            response = result.data

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
            response = result.data

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
            note = note_result.data

        assert note.key
        assert note.parent_key == item_key

        async with Client(mcp) as client:
            notes_result = await client.call_tool(
                "get_item_notes",
                arguments={"item_key": item_key},
            )
            notes = notes_result.data

        note_keys = [n["key"] for n in notes]
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
                parent_data = parent_result.data
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
                sub_data = sub_result.data
                assert sub_data["key"]
                sub_key = sub_data["key"]

            # Add items to the subcollection via test_data_manager.
            sub_items = await test_data_manager.create_test_items(
                count=3, collection_key=sub_key
            )
            assert len(sub_items) == 3

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "get_collection_items",
                    arguments={
                        "collection_key": parent_key,
                        "include_subcollections": True,
                    },
                )
                response = result.data

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
                arguments={"search_params": {"item_type": "journalArticle"}},
            )
            response = result.data

        assert isinstance(response.items, list)
        for item in response.items:
            assert item.data.itemType == "journalArticle"


# ---------------------------------------------------------------------------
# Class 3: TestDoiSearchAndCreate
# ---------------------------------------------------------------------------

_DOI = "10.1038/nature12373"


class TestDoiSearchAndCreate:
    """End-to-end tests for the add_item_by_doi MCP tool.

    Every test skips when TEST_ZOTERO_LIBRARY_ID / TEST_ZOTERO_API_KEY are absent.
    """

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
                item = result.data

            assert item.key
            assert item.data.title
            assert item.data.DOI == _DOI
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
                collection_data = coll_result.data
                assert collection_data["key"]
                collection_key = collection_data["key"]

            async with Client(mcp) as client:
                item_result = await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": _DOI, "collection_key": collection_key},
                )
                item = item_result.data
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
                item = result.data

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
                item = result.data

            # Search using a unique title fragment — "Nanometre" is specific enough
            # to target only this DOI item in the library.
            async with Client(mcp) as client:
                search_result = await client.call_tool(
                    "search_articles",
                    arguments={"search_params": {"q": "Nanometre-scale thermometry"}},
                )
                response = search_result.data

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
            with pytest.raises(Exception):
                await client.call_tool(
                    "add_item_by_doi",
                    arguments={"doi": "not-a-doi"},
                )
