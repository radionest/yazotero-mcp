"""Tests for offset-based pagination (_fetch_all_paginated)."""

import asyncio
from unittest.mock import MagicMock

import pytest

from yazot.zotero_client import _ZOTERO_PAGE_LIMIT, _fetch_all_paginated


def _make_mock_client(pages: list[list[dict]]) -> MagicMock:
    """Create a mock pyzotero client that returns pages sequentially."""
    client = MagicMock()
    call_count = 0

    def top_side_effect(*args, **kwargs):
        nonlocal call_count
        page = pages[call_count] if call_count < len(pages) else []
        call_count += 1
        return page

    client.top = MagicMock(side_effect=top_side_effect)
    client.collections = MagicMock(side_effect=top_side_effect)
    client.collection_items_top = MagicMock(side_effect=top_side_effect)
    return client


@pytest.fixture
def items_page() -> list[dict]:
    """A full page of 100 items."""
    return [{"key": f"ITEM{i:04d}", "data": {}} for i in range(_ZOTERO_PAGE_LIMIT)]


@pytest.fixture
def partial_page() -> list[dict]:
    """A partial page (< 100 items) signaling end of pagination."""
    return [{"key": f"LAST{i:02d}", "data": {}} for i in range(30)]


async def test_single_page_no_pagination(partial_page):
    """Single page with fewer items than limit — no further requests."""
    client = _make_mock_client([partial_page])
    result = await _fetch_all_paginated(client, "top", None)
    assert len(result) == 30
    assert client.top.call_count == 1
    _, kwargs = client.top.call_args
    assert kwargs["limit"] == _ZOTERO_PAGE_LIMIT
    assert kwargs["start"] == 0


async def test_multi_page_pagination(items_page, partial_page):
    """Multiple full pages followed by a partial page."""
    client = _make_mock_client([items_page, items_page, partial_page])
    result = await _fetch_all_paginated(client, "top", None)
    assert len(result) == _ZOTERO_PAGE_LIMIT * 2 + 30
    assert client.top.call_count == 3
    # Verify start offsets
    starts = [call.kwargs["start"] for call in client.top.call_args_list]
    assert starts == [0, _ZOTERO_PAGE_LIMIT, _ZOTERO_PAGE_LIMIT * 2]


async def test_empty_result():
    """Empty library returns empty list without errors."""
    client = _make_mock_client([[]])
    result = await _fetch_all_paginated(client, "top", None)
    assert result == []
    assert client.top.call_count == 1


async def test_exactly_one_full_page(items_page):
    """Exactly one full page — must fetch a second (empty) page to confirm end."""
    client = _make_mock_client([items_page, []])
    result = await _fetch_all_paginated(client, "top", None)
    assert len(result) == _ZOTERO_PAGE_LIMIT
    assert client.top.call_count == 2


async def test_api_params_forwarded(partial_page):
    """Extra api_params (e.g. search query) are forwarded to every page request."""
    client = _make_mock_client([partial_page])
    await _fetch_all_paginated(client, "top", None, q="test query", qmode="everything")
    _, kwargs = client.top.call_args
    assert kwargs["q"] == "test query"
    assert kwargs["qmode"] == "everything"
    assert kwargs["limit"] == _ZOTERO_PAGE_LIMIT


async def test_api_params_limit_overridden(partial_page):
    """User-supplied limit is overridden by _ZOTERO_PAGE_LIMIT."""
    client = _make_mock_client([partial_page])
    await _fetch_all_paginated(client, "top", None, limit=25)
    _, kwargs = client.top.call_args
    assert kwargs["limit"] == _ZOTERO_PAGE_LIMIT


async def test_collection_items_top_with_positional_arg(partial_page):
    """Positional args (e.g. collection key) are passed through."""
    client = _make_mock_client([partial_page])
    await _fetch_all_paginated(client, "collection_items_top", None, "COL_KEY")
    args, kwargs = client.collection_items_top.call_args
    assert args == ("COL_KEY",)
    assert kwargs["limit"] == _ZOTERO_PAGE_LIMIT


async def test_semaphore_limits_concurrent_requests(items_page, partial_page):
    """Semaphore limits concurrent HTTP requests across interleaved paginations."""
    semaphore = asyncio.Semaphore(2)
    max_concurrent = 0
    current_concurrent = 0

    def tracking_top(*args, **kwargs):
        nonlocal max_concurrent, current_concurrent
        current_concurrent += 1
        max_concurrent = max(max_concurrent, current_concurrent)
        # Simulate pages: first call returns full page, second returns partial
        start = kwargs.get("start", 0)
        result = items_page if start == 0 else partial_page
        current_concurrent -= 1
        return result

    client1 = MagicMock()
    client1.top = MagicMock(side_effect=tracking_top)
    client2 = MagicMock()
    client2.top = MagicMock(side_effect=tracking_top)

    # Run two paginations concurrently with shared semaphore
    await asyncio.gather(
        _fetch_all_paginated(client1, "top", semaphore),
        _fetch_all_paginated(client2, "top", semaphore),
    )
    assert max_concurrent <= 2


async def test_error_propagation():
    """Errors from pyzotero are propagated without swallowing."""
    client = MagicMock()
    client.top = MagicMock(side_effect=RuntimeError("API error"))
    with pytest.raises(RuntimeError, match="API error"):
        await _fetch_all_paginated(client, "top", None)
