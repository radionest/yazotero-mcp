import contextlib
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from fastmcp import Client

from yazot.config import Settings
from yazot.mcp_server import mcp
from yazot.models import ZoteroItem
from yazot.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.e2e.test_helpers import ZoteroTestDataManager

_THIS_DIR = str(Path(__file__).parent)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_marker = (
        pytest.mark.skip(reason="TEST_ZOTERO_API_KEY not set")
        if not os.getenv("TEST_ZOTERO_API_KEY")
        else None
    )
    for item in items:
        if str(item.fspath).startswith(_THIS_DIR):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.xdist_group("zotero"))
            if skip_marker is not None:
                item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test configuration using real Zotero sandbox."""
    return Settings(
        zotero_local=os.getenv("TEST_ZOTERO_LOCAL", "false").lower() == "true",
        zotero_library_id=os.getenv("TEST_ZOTERO_LIBRARY_ID", ""),
        zotero_api_key=os.getenv("TEST_ZOTERO_API_KEY"),
        zotero_library_type=os.getenv("TEST_ZOTERO_LIBRARY_TYPE", "user"),
        max_chunk_size=5000,
    )


@pytest.fixture(scope="session")
async def test_zotero_client(test_settings: Settings) -> AsyncGenerator[ZoteroClient, None]:
    """Web Zotero client for E2E tests."""
    web_settings = Settings(
        zotero_local=False,
        zotero_library_id=test_settings.zotero_library_id,
        zotero_api_key=test_settings.zotero_api_key,
        zotero_library_type=test_settings.zotero_library_type,
        max_chunk_size=test_settings.max_chunk_size,
    )
    test_client = ZoteroClient(web_settings)
    yield test_client
    test_client.cache.clear()


@pytest.fixture
async def fresh_zotero_client(test_settings: Settings) -> ZoteroClient:
    """Per-test web client without HTTP cache from prior requests."""
    return ZoteroClient(
        Settings(
            zotero_local=False,
            zotero_library_id=test_settings.zotero_library_id,
            zotero_api_key=test_settings.zotero_api_key,
            zotero_library_type=test_settings.zotero_library_type,
            max_chunk_size=test_settings.max_chunk_size,
        )
    )


@pytest.fixture
async def test_collection_key() -> str:
    """Key of test collection with sample data."""
    return os.getenv("TEST_COLLECTION_KEY", "TESTCOLL")


@pytest.fixture(scope="session")
async def item_with_pdf_key(
    test_data_manager: "ZoteroTestDataManager",
    test_zotero_client: ZoteroClient,
) -> str:
    """Create a test item with a real uploaded PDF and return its key."""
    items = await test_data_manager.create_test_items(1)
    item = items[0]
    pdf_path = str(Path(__file__).parent.parent / "fixtures" / "test_article.pdf")
    await test_zotero_client.attach_pdf(item.key, pdf_path)
    return item.key


@pytest.fixture
async def test_item_with_pdf(test_data_manager: "ZoteroTestDataManager") -> str:
    """Create test item with PDF attachment and return its key."""
    item = await test_data_manager.create_item_with_attachment(
        title="E2E Test Article with PDF",
        attachment_url="https://arxiv.org/pdf/1706.03762.pdf",
    )
    return item.key


@pytest.fixture
async def test_item_without_pdf(test_data_manager: "ZoteroTestDataManager") -> str:
    """Create test item without attachments and return its key."""
    items = await test_data_manager.create_test_items(
        count=1,
        template_type="journalArticle",
    )
    return items[0].key


@pytest.fixture
async def mcp_client() -> AsyncGenerator[Client, None]:
    """Per-test MCP client — all tool calls in one test go through this."""
    async with Client(mcp) as client:
        yield client


@pytest.fixture(scope="function")
async def setup_test_data(
    test_zotero_client: ZoteroClient,
) -> AsyncGenerator[dict[str, Any], None]:
    """Setup test data in real Zotero and cleanup after test."""
    created_items: list[str] = []

    def track_item(item_key: str) -> None:
        created_items.append(item_key)

    test_data: dict[str, Any] = {
        "track_item": track_item,
        "created_items": created_items,
    }

    yield test_data

    if created_items and test_zotero_client.mode != "local":
        for item_key in created_items:
            with contextlib.suppress(Exception):
                await test_zotero_client.delete_item_by_key(item_key)


@pytest.fixture(scope="session")
async def test_data_manager(
    test_zotero_client: ZoteroClient,
) -> AsyncGenerator["ZoteroTestDataManager", None]:
    """Provide test data manager with automatic cleanup."""
    from tests.e2e.test_helpers import ZoteroTestDataManager

    manager = ZoteroTestDataManager(test_zotero_client)
    yield manager
    await manager.cleanup()


@pytest.fixture
async def large_test_collection(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create a large test collection for stress testing."""
    collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Large Test Collection"
    )
    collection_key = collection_keys[0]
    item_count = 1000
    await test_data_manager.create_test_items(item_count, collection_key)
    yield collection_key, item_count


@pytest.fixture
async def nested_collections_structure(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[dict[str, list[str]], None]:
    """Create nested collection structure for testing."""
    hierarchy = await test_data_manager.create_nested_collections(
        depth=3, width=3, root_name="Nested Test Root"
    )
    yield hierarchy


# E2E Search test fixtures


@pytest.fixture
async def basic_collection_with_items(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create basic collection with 10 items for simple search tests."""
    collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Basic Search Test"
    )
    collection_key = collection_keys[0]
    item_count = 10
    await test_data_manager.create_test_items(item_count, collection_key)
    yield collection_key, item_count


@pytest.fixture
async def collection_for_query_test(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[str, None]:
    """Create collection with items for query filtering tests."""
    collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Query Filter Test"
    )
    collection_key = collection_keys[0]
    await test_data_manager.create_test_items(5, collection_key)
    yield collection_key


@pytest.fixture
async def collection_for_fulltext_test(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[str, None]:
    """Create collection with items for fulltext extraction tests."""
    collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Fulltext Test"
    )
    collection_key = collection_keys[0]
    await test_data_manager.create_test_items(5, collection_key)
    yield collection_key


@pytest.fixture
async def collection_for_chunking_test(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[str, None]:
    """Create collection with 20 items for chunking tests."""
    collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Chunking Test"
    )
    collection_key = collection_keys[0]
    await test_data_manager.create_test_items(20, collection_key)
    yield collection_key


@pytest.fixture
async def collection_for_cache_test(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[str, None]:
    """Create collection with 10 items for cache behavior tests."""
    collection_keys = await test_data_manager.create_test_collections(1, name_prefix="Cache Test")
    collection_key = collection_keys[0]
    await test_data_manager.create_test_items(10, collection_key)
    yield collection_key


# Stress test fixtures


@pytest.fixture
async def nested_collections_with_items(
    nested_collections_structure: dict[str, list[str]],
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[dict[str, list[str]], None]:
    """Create nested collections with items in leaf nodes."""
    leaf_collections = nested_collections_structure["level_2"]
    for coll_key in leaf_collections:
        await test_data_manager.create_test_items(50, coll_key)
    yield nested_collections_structure


@pytest.fixture
async def multiple_collections_for_concurrent_test(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[list[str], None]:
    """Create 5 collections with 20 items each for concurrent tests."""
    num_collections = 5
    collection_keys = await test_data_manager.create_test_collections(num_collections)
    for coll_key in collection_keys:
        await test_data_manager.create_test_items(20, coll_key)
    yield collection_keys


@pytest.fixture
async def bulk_test_collections(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[list[str], None]:
    """Create 120 collections for bulk operation tests."""
    collections = await test_data_manager.create_test_collections(120)
    yield collections


@pytest.fixture(scope="session")
async def bulk_test_items(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[list[ZoteroItem], None]:
    """Create 150 items for bulk operation tests."""
    items = await test_data_manager.create_test_items(150)
    yield items


@pytest.fixture
async def collection_with_exact_count(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create collection with exactly 42 items for count verification."""
    collection_keys = await test_data_manager.create_test_collections(1)
    collection_key = collection_keys[0]
    item_count = 42
    await test_data_manager.create_test_items(item_count, collection_key)
    yield collection_key, item_count


@pytest.fixture
async def collection_for_fulltext_batch(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[str, None]:
    """Create collection with 50 items for fulltext batch tests."""
    collection_keys = await test_data_manager.create_test_collections(1)
    collection_key = collection_keys[0]
    await test_data_manager.create_test_items(50, collection_key)
    yield collection_key


# Configuration fixtures


@pytest.fixture
def chunker_with_small_size(monkeypatch: pytest.MonkeyPatch) -> int:
    """Set small chunk size via env var for testing chunking behavior."""
    small_size = 100
    monkeypatch.setenv("MAX_CHUNK_SIZE", str(small_size))
    return small_size


@pytest.fixture
def chunker_with_stress_size(monkeypatch: pytest.MonkeyPatch) -> int:
    """Set chunk size for stress testing (5KB) via env var."""
    stress_size = 5000
    monkeypatch.setenv("MAX_CHUNK_SIZE", str(stress_size))
    return stress_size


@pytest.fixture
async def collection_key_items_with_tags(
    test_data_manager: "ZoteroTestDataManager",
) -> str:
    """Create test items with various tag types."""
    new_collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Test Tags"
    )
    await test_data_manager.create_items_with_various_tags(collection_key=new_collection_keys[0])
    return new_collection_keys[0]


# Subcollection test fixtures


@pytest.fixture
async def nested_collection_with_items(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int, int], None]:
    """Create parent collection with items and subcollection with items."""
    parent_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Parent Collection"
    )
    parent_key = parent_keys[0]
    parent_items = await test_data_manager.create_test_items(5, parent_key)
    parent_count = len(parent_items)

    sub_keys = await test_data_manager.create_test_collections(
        1, parent_key=parent_key, name_prefix="Sub Collection"
    )
    sub_key = sub_keys[0]
    sub_items = await test_data_manager.create_test_items(3, sub_key)
    sub_count = len(sub_items)

    total_count = parent_count + sub_count
    yield parent_key, parent_count, total_count


@pytest.fixture
async def deeply_nested_collection(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, dict[str, int]], None]:
    """Create deeply nested collection structure (4 levels) with items at each level."""
    root_keys = await test_data_manager.create_test_collections(1, name_prefix="Deep Root")
    root_key = root_keys[0]
    root_items = await test_data_manager.create_test_items(2, root_key)

    counts = {"level_0": len(root_items)}

    level1_keys = await test_data_manager.create_test_collections(
        2, parent_key=root_key, name_prefix="Deep L1"
    )
    level1_count = 0
    for key in level1_keys:
        items = await test_data_manager.create_test_items(3, key)
        level1_count += len(items)
    counts["level_1"] = level1_count

    level2_keys = await test_data_manager.create_test_collections(
        2, parent_key=level1_keys[0], name_prefix="Deep L2"
    )
    level2_count = 0
    for key in level2_keys:
        items = await test_data_manager.create_test_items(2, key)
        level2_count += len(items)
    counts["level_2"] = level2_count

    level3_keys = await test_data_manager.create_test_collections(
        1, parent_key=level2_keys[0], name_prefix="Deep L3"
    )
    level3_items = await test_data_manager.create_test_items(1, level3_keys[0])
    counts["level_3"] = len(level3_items)

    yield root_key, counts


@pytest.fixture
async def collection_with_duplicate_items(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int, int], None]:
    """Create parent with subcollections where some items appear in multiple collections."""
    parent_keys = await test_data_manager.create_test_collections(1, name_prefix="Duplicate Parent")
    parent_key = parent_keys[0]

    unique_items = await test_data_manager.create_test_items(5)

    await test_data_manager.add_items_to_collection(unique_items[:3], parent_key)
    unique_items = await test_data_manager.refresh_items(unique_items)

    sub_keys = await test_data_manager.create_test_collections(
        2, parent_key=parent_key, name_prefix="Duplicate Sub"
    )

    await test_data_manager.add_items_to_collection(unique_items[:4], sub_keys[0])
    unique_items = await test_data_manager.refresh_items(unique_items)

    await test_data_manager.add_items_to_collection(unique_items[2:], sub_keys[1])

    unique_count = 5
    total_appearances = 10
    yield parent_key, unique_count, total_appearances


@pytest.fixture
async def collection_with_empty_subcollections(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create parent collection with items and empty subcollections."""
    parent_keys = await test_data_manager.create_test_collections(1, name_prefix="Empty Sub Parent")
    parent_key = parent_keys[0]
    parent_items = await test_data_manager.create_test_items(4, parent_key)

    await test_data_manager.create_test_collections(
        3, parent_key=parent_key, name_prefix="Empty Sub"
    )

    yield parent_key, len(parent_items)


@pytest.fixture
async def large_nested_collection(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create parent collection with multiple subcollections for chunking tests."""
    parent_keys = await test_data_manager.create_test_collections(1, name_prefix="Large Nested")
    parent_key = parent_keys[0]
    await test_data_manager.create_test_items(10, parent_key)

    sub_keys = await test_data_manager.create_test_collections(
        5, parent_key=parent_key, name_prefix="Large Sub"
    )
    for sub_key in sub_keys:
        await test_data_manager.create_test_items(8, sub_key)

    total_count = 10 + 5 * 8
    yield parent_key, total_count
