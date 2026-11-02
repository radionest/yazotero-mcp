"""Unit tests for ZoteroTestDataManager batch cleanup (e2e test helper).

Regression coverage for sandbox accumulation: cleanup() must delete items and
collections in batches of 50 via pyzotero's batch delete APIs, fetching a fresh
library version before every batch.
"""

import itertools
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from tests.e2e.test_helpers import ZoteroTestDataManager
from yazot.models import ZoteroItem, ZoteroItemData


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
