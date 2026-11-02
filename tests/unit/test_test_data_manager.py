"""Unit tests for ZoteroTestDataManager (e2e test helper).

Regression coverage for sandbox accumulation: cleanup() must delete items and
collections in batches of 50 via pyzotero's batch delete APIs, fetching a fresh
library version before every batch.

Issue #62 regression: create_test_items() must embed collection membership in
the initial ItemCreate payload instead of adding items to the collection
after creation (post-creation add_to_collection could silently lose
membership for some items).
"""

import itertools
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from tests.e2e.test_helpers import ZoteroTestDataManager
from yazot.models import ItemCreate, ZoteroItem, ZoteroItemData


def _make_item(index: int) -> ZoteroItem:
    return ZoteroItem(
        key=f"item-{index}",
        version=1,
        data=ZoteroItemData(item_type="journalArticle", title=f"Item {index}"),
    )


def _make_web_client() -> MagicMock:
    """Mock ZoteroClient in web mode with an instrumented _call."""
    client = MagicMock()
    client.mode = "web"
    client.delete_item_by_key = AsyncMock()
    client.delete_collection_by_key = AsyncMock()
    return client


async def test_cleanup_batches_items_and_collections() -> None:
    """120 items + 120 collections -> 50/50/remainder batches, fresh version per batch.

    Collections must be deleted in reverse creation order. Only successfully
    deleted objects are counted and tracking lists are cleared afterwards.
    """
    client = _make_web_client()
    manager = ZoteroTestDataManager(client)

    manager.created_items = [_make_item(i) for i in range(120)]
    manager.created_collections = [f"coll-{i}" for i in range(120)]

    versions = itertools.count(100)
    events: list[tuple[Any, ...]] = []

    async def call_side_effect(func: Any, *args: Any, **kwargs: Any) -> Any:
        if func is client._client.last_modified_version:
            version = next(versions)
            events.append(("version", version))
            return version
        if func is client._client.delete_item:
            events.append(("item_delete", args[0], kwargs["last_modified"]))
            return None
        if func is client._client.delete_collection:
            events.append(("coll_delete", args[0], kwargs["last_modified"]))
            return None
        raise AssertionError(f"unexpected _call func: {func!r}")

    client._call = AsyncMock(side_effect=call_side_effect)

    result = await manager.cleanup()

    assert events == [
        ("version", 100),
        ("item_delete", [{"key": f"item-{i}"} for i in range(0, 50)], 100),
        ("version", 101),
        ("item_delete", [{"key": f"item-{i}"} for i in range(50, 100)], 101),
        ("version", 102),
        ("item_delete", [{"key": f"item-{i}"} for i in range(100, 120)], 102),
        ("version", 103),
        ("coll_delete", [{"key": f"coll-{i}"} for i in range(119, 69, -1)], 103),
        ("version", 104),
        ("coll_delete", [{"key": f"coll-{i}"} for i in range(69, 19, -1)], 104),
        ("version", 105),
        ("coll_delete", [{"key": f"coll-{i}"} for i in range(19, -1, -1)], 105),
    ]
    assert result == {"items": 120, "collections": 120}
    assert manager.created_items == []
    assert manager.created_collections == []
    client.delete_item_by_key.assert_not_called()
    client.delete_collection_by_key.assert_not_called()


async def test_cleanup_is_noop_in_local_mode() -> None:
    """Local mode must not touch the API at all."""
    client = _make_web_client()
    client.mode = "local"
    manager = ZoteroTestDataManager(client)

    manager.created_items = [_make_item(i) for i in range(3)]
    manager.created_collections = ["coll-0", "coll-1"]

    result = await manager.cleanup()

    assert result == {"items": 0, "collections": 0}
    client._call.assert_not_called()


async def test_cleanup_continues_after_failed_batch() -> None:
    """A failing batch must not abort cleanup; only successfully deleted objects count."""
    client = _make_web_client()
    manager = ZoteroTestDataManager(client)

    manager.created_items = [_make_item(i) for i in range(120)]
    manager.created_collections = [f"coll-{i}" for i in range(120)]

    versions = itertools.count(100)

    async def call_side_effect(func: Any, *args: Any, **kwargs: Any) -> Any:
        if func is client._client.last_modified_version:
            return next(versions)
        if func is client._client.delete_item:
            # Middle item batch fails; others succeed.
            if args[0][0]["key"] == "item-50":
                raise RuntimeError("simulated batch delete failure")
            return None
        if func is client._client.delete_collection:
            if args[0][0]["key"] == "coll-69":
                raise RuntimeError("simulated batch delete failure")
            return None
        raise AssertionError(f"unexpected _call func: {func!r}")

    client._call = AsyncMock(side_effect=call_side_effect)

    result = await manager.cleanup()

    assert result == {"items": 70, "collections": 70}
    assert manager.created_items == []
    assert manager.created_collections == []


def _make_creation_client() -> MagicMock:
    """Mock ZoteroClient for item-creation flows.

    get_item_template returns a minimal journalArticle template; create_items
    and add_to_collection are AsyncMocks so tests can assert call behavior.
    """
    client = MagicMock()
    client.mode = "web"
    client.get_item_template = AsyncMock(
        return_value={
            "itemType": "journalArticle",
            "title": "",
            "abstractNote": "",
            "date": "",
            "creators": [],
            "tags": [],
            "collections": [],
        }
    )
    client.create_items = AsyncMock()
    client.add_to_collection = AsyncMock()
    return client


def _created_batch(client: MagicMock) -> list[ItemCreate]:
    """Extract the single batch of ItemCreate models passed to client.create_items."""
    client.create_items.assert_awaited_once()
    (batch,) = client.create_items.call_args.args
    return cast("list[ItemCreate]", batch)


async def test_create_test_items_embeds_collection_in_initial_payload() -> None:
    """Issue #62 regression: with collection_key, membership must be set at creation.

    The create payload must carry collections=[collection_key] and
    add_to_collection must not be called afterwards (it could silently lose
    membership for some items).
    """
    client = _make_creation_client()
    created = [_make_item(i) for i in range(3)]
    client.create_items = AsyncMock(return_value=created)

    manager = ZoteroTestDataManager(client)
    items = await manager.create_test_items(3, collection_key="COLLKEY")

    assert items == created
    assert manager.created_items == created
    batch = _created_batch(client)
    assert len(batch) == 3
    assert all(isinstance(model, ItemCreate) for model in batch)
    assert all(model.collections == ["COLLKEY"] for model in batch)
    client.add_to_collection.assert_not_awaited()


async def test_create_test_items_without_collection_keeps_empty_collections() -> None:
    """Without collection_key, items are created with empty collections and no add call."""
    client = _make_creation_client()
    created = [_make_item(i) for i in range(2)]
    client.create_items = AsyncMock(return_value=created)

    manager = ZoteroTestDataManager(client)
    items = await manager.create_test_items(2)

    assert items == created
    assert manager.created_items == created
    batch = _created_batch(client)
    assert len(batch) == 2
    assert all(model.collections == [] for model in batch)
    client.add_to_collection.assert_not_awaited()
