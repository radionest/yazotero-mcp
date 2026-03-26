import contextlib
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from fastmcp import Context

from yazot.config import Settings
from yazot.models import ZoteroItem
from yazot.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.test_helpers import ZoteroTestDataManager


@pytest.fixture(scope="session", autouse=True)
def load_test_env() -> None:
    """Automatically load .env.test for all tests in the session.

    Also copies TEST_ZOTERO_* values to ZOTERO_* to isolate MCP lifespan
    from production .env credentials. Without this, Client(mcp) → app_lifespan
    → Settings() would read production tokens from .env.
    """
    env_test_path = os.path.join(os.path.dirname(__file__), "..", ".env.test")
    if os.path.exists(env_test_path):
        load_dotenv(env_test_path, override=True)
    else:
        load_dotenv(".env.test", override=True)

    # Isolate MCP lifespan from production .env:
    # Copy TEST_ZOTERO_* → ZOTERO_* so Settings() uses test credentials
    for suffix in ("LOCAL", "LIBRARY_ID", "API_KEY", "LIBRARY_TYPE"):
        test_val = os.environ.get(f"TEST_ZOTERO_{suffix}")
        if test_val is not None:
            os.environ[f"ZOTERO_{suffix}"] = test_val


@pytest.fixture
def local_settings() -> Settings:
    """Settings for local Zotero mode."""
    return Settings(
        zotero_local=True,
        zotero_library_id="0",
        zotero_api_key=None,
        zotero_library_type="user",
    )


@pytest.fixture
def web_settings() -> Settings:
    """Settings for web Zotero mode."""
    return Settings(
        zotero_local=False,
        zotero_library_id="123456",
        zotero_api_key="test_api_key_123",
        zotero_library_type="user",
    )


@pytest.fixture
def local_test_client(local_settings: Settings) -> ZoteroClient:
    """Local Zotero client for testing router behavior.

    Only used in tests that specifically test local client functionality,
    such as test_client_router.py. Most E2E tests should use test_zotero_client
    which provides web API access.
    """
    return ZoteroClient(local_settings)


@pytest.fixture
def local_zotero_client(local_settings: Settings) -> ZoteroClient:
    """Local Zotero client for server startup tests."""
    return ZoteroClient(local_settings)


@pytest.fixture
def web_zotero_client(web_settings: Settings) -> ZoteroClient:
    """Web Zotero client for server startup tests."""
    with patch("yazot.zotero_client.zotero.Zotero") as mock_zotero:
        mock_zotero.return_value = MagicMock()
        return ZoteroClient(web_settings)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test configuration using real Zotero sandbox."""
    load_dotenv(".env.test", override=True)

    # Use either test Zotero account or local SQLite
    return Settings(
        zotero_local=os.getenv("TEST_ZOTERO_LOCAL", "false").lower() == "true",
        zotero_library_id=os.getenv("TEST_ZOTERO_LIBRARY_ID", ""),
        zotero_api_key=os.getenv("TEST_ZOTERO_API_KEY"),
        zotero_library_type=os.getenv("TEST_ZOTERO_LIBRARY_TYPE", "user"),
        max_chunk_size=5000,  # Smaller chunks for testing
    )


@pytest.fixture(scope="session")
async def test_zotero_client(test_settings: Settings) -> AsyncGenerator[ZoteroClient, None]:
    """Web Zotero client for E2E tests.

    Creates a web API client using test credentials. Used by test_data_manager
    and other E2E fixtures for real CRUD operations against Zotero API.
    The MCP server uses lifespan to create its own dependencies from .env.test.
    """
    # Force web mode for tests (override test_settings if needed)
    web_settings = Settings(
        zotero_local=False,  # Always use web API for E2E tests
        zotero_library_id=test_settings.zotero_library_id,
        zotero_api_key=test_settings.zotero_api_key,
        zotero_library_type=test_settings.zotero_library_type,
        max_chunk_size=test_settings.max_chunk_size,
    )

    test_client = ZoteroClient(web_settings)

    yield test_client

    test_client.cache.clear()


@pytest.fixture
async def test_collection_key() -> str:
    """Key of test collection with sample data."""
    # This should be created once in your test Zotero account
    return os.getenv("TEST_COLLECTION_KEY", "TESTCOLL")


@pytest.fixture
async def test_item_with_pdf(test_data_manager: "ZoteroTestDataManager") -> str:
    """Create test item with PDF attachment and return its key."""
    item = await test_data_manager.create_item_with_attachment(
        title="E2E Test Article with PDF",
        attachment_url="https://arxiv.org/pdf/1706.03762.pdf",  # Real PDF for testing
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
async def mcp_context(test_settings: Settings) -> Context:
    """Create MCP context for tool testing with lifespan_context.

    Sets up the request context var so ctx.request_context.lifespan_context
    is available, matching the pattern used by the lifespan in production.
    """
    from mcp.server.fastmcp.server import RequestContext, request_ctx

    from yazot.chunker import ResponseChunker, TextChunker
    from yazot.client_router import ZoteroClientRouter
    from yazot.crossref_client import CrossrefClient
    from yazot.mcp_server import mcp as server
    from yazot.note_manager import NoteManager

    router = ZoteroClientRouter(test_settings)
    crossref = CrossrefClient()
    chunker = ResponseChunker(max_tokens=test_settings.max_chunk_size)
    text_chunker = TextChunker(max_tokens=test_settings.max_chunk_size)
    note_manager = NoteManager(router)

    lifespan_context = {
        "settings": test_settings,
        "router": router,
        "crossref": crossref,
        "chunker": chunker,
        "text_chunker": text_chunker,
        "note_manager": note_manager,
    }

    # Set the request context var so ctx.request_context works
    request_ctx.set(
        RequestContext(
            request_id="test-request",
            meta=None,
            session=None,  # type: ignore[arg-type]
            lifespan_context=lifespan_context,
        )
    )

    return Context(server)


@pytest.fixture(scope="function")
async def setup_test_data(test_zotero_client: ZoteroClient) -> AsyncGenerator[dict[str, Any], None]:
    """Setup test data in real Zotero and cleanup after test."""
    created_items = []

    # Helper to track created items for cleanup
    def track_item(item_key: str) -> None:
        created_items.append(item_key)

    test_data = {
        "track_item": track_item,
        "created_items": created_items,
    }

    yield test_data

    # Cleanup: delete created items (only in web mode)
    if created_items and test_zotero_client.mode != "local":
        for item_key in created_items:
            with contextlib.suppress(Exception):
                await test_zotero_client.delete_item_by_key(item_key)


@pytest.fixture(scope="session")
async def test_data_manager(
    test_zotero_client: ZoteroClient,
) -> AsyncGenerator["ZoteroTestDataManager", None]:
    """Provide test data manager with automatic cleanup.

    Example usage:
        async def test_something(test_data_manager):
            # Create test items
            items = test_data_manager.create_test_items(100)
            # Test logic here
            # Cleanup happens automatically
    """
    from tests.test_helpers import ZoteroTestDataManager

    manager = ZoteroTestDataManager(test_zotero_client)

    yield manager

    # Cleanup all created data
    await manager.cleanup()


@pytest.fixture
async def large_test_collection(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create a large test collection for stress testing.

    Returns:
        Tuple of (collection_key, item_count)
    """
    # Create one collection with many items
    collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Large Test Collection"
    )
    collection_key = collection_keys[0]

    # Create 1000 items in the collection
    item_count = 1000
    await test_data_manager.create_test_items(item_count, collection_key)

    yield collection_key, item_count

    # Cleanup handled by test_data_manager fixture


@pytest.fixture
async def nested_collections_structure(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[dict[str, list[str]], None]:
    """Create nested collection structure for testing.

    Returns:
        Dictionary mapping level names to collection keys
    """
    # Create 3 levels deep, 3 collections per level
    hierarchy = await test_data_manager.create_nested_collections(
        depth=3, width=3, root_name="Nested Test Root"
    )

    yield hierarchy

    # Cleanup handled by test_data_manager fixture


# E2E Search test fixtures - provide ready-made test data


@pytest.fixture
async def basic_collection_with_items(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create basic collection with 10 items for simple search tests.

    Returns:
        Tuple of (collection_key, item_count)
    """
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
    """Create collection with items for query filtering tests.

    Returns:
        Collection key with 5 items containing 'Test' in titles
    """
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
    """Create collection with items for fulltext extraction tests.

    Returns:
        Collection key with 5 items
    """
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
    """Create collection with 20 items for chunking tests.

    Returns:
        Collection key with 20 items
    """
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
    """Create collection with 10 items for cache behavior tests.

    Returns:
        Collection key with 10 items
    """
    collection_keys = await test_data_manager.create_test_collections(1, name_prefix="Cache Test")
    collection_key = collection_keys[0]
    await test_data_manager.create_test_items(10, collection_key)

    yield collection_key


# Stress test fixtures - provide ready-made complex data structures


@pytest.fixture
async def nested_collections_with_items(
    nested_collections_structure: dict[str, list[str]],
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[dict[str, list[str]], None]:
    """Create nested collections with items in leaf nodes.

    Returns:
        Dictionary mapping level names to collection keys (with items in level_2)
    """
    # Add 50 items to each leaf collection
    leaf_collections = nested_collections_structure["level_2"]
    for coll_key in leaf_collections:
        await test_data_manager.create_test_items(50, coll_key)

    yield nested_collections_structure


@pytest.fixture
async def multiple_collections_for_concurrent_test(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[list[str], None]:
    """Create 5 collections with 20 items each for concurrent tests.

    Returns:
        List of collection keys
    """
    num_collections = 5
    collection_keys = await test_data_manager.create_test_collections(num_collections)
    for coll_key in collection_keys:
        await test_data_manager.create_test_items(20, coll_key)

    yield collection_keys


@pytest.fixture
async def bulk_test_collections(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[list[str], None]:
    """Create 120 collections for bulk operation tests.

    Returns:
        List of 120 collection keys
    """
    collections = await test_data_manager.create_test_collections(120)

    yield collections


@pytest.fixture(scope="session")
async def bulk_test_items(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[list[ZoteroItem], None]:
    """Create 150 items for bulk operation tests.

    Returns:
        List of 150 item keys
    """
    items = await test_data_manager.create_test_items(150)

    yield items


@pytest.fixture
async def collection_with_exact_count(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create collection with exactly 42 items for count verification.

    Returns:
        Tuple of (collection_key, item_count=42)
    """
    collection_keys = await test_data_manager.create_test_collections(1)
    collection_key = collection_keys[0]
    item_count = 42
    await test_data_manager.create_test_items(item_count, collection_key)

    yield collection_key, item_count


@pytest.fixture
async def collection_for_fulltext_batch(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[str, None]:
    """Create collection with 50 items for fulltext batch tests.

    Returns:
        Collection key with 50 items
    """
    collection_keys = await test_data_manager.create_test_collections(1)
    collection_key = collection_keys[0]
    await test_data_manager.create_test_items(50, collection_key)

    yield collection_key


# Configuration fixtures - manage temporary state changes


@pytest.fixture
def chunker_with_small_size(monkeypatch: pytest.MonkeyPatch) -> int:
    """Set small chunk size via env var for testing chunking behavior.

    The lifespan reads MAX_CHUNK_SIZE from Settings, so setting the env var
    before creating a Client(mcp) session will take effect.

    Returns:
        The small chunk size (100 tokens)
    """
    small_size = 100
    monkeypatch.setenv("MAX_CHUNK_SIZE", str(small_size))
    return small_size


@pytest.fixture
def chunker_with_stress_size(monkeypatch: pytest.MonkeyPatch) -> int:
    """Set chunk size for stress testing (5KB) via env var.

    Returns:
        The stress test chunk size (5000 tokens)
    """
    stress_size = 5000
    monkeypatch.setenv("MAX_CHUNK_SIZE", str(stress_size))
    return stress_size


@pytest.fixture
async def collection_key_items_with_tags(
    test_data_manager: "ZoteroTestDataManager",
) -> str:
    """Create test items with various tag types.

    Returns:
        Key of collection containing items
    """
    new_collection_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Test Tags"
    )
    items = await test_data_manager.create_items_with_various_tags(
        collection_key=new_collection_keys[0]
    )
    return new_collection_keys[0]
    # Cleanup handled by test_data_manager fixture


# Subcollection test fixtures


@pytest.fixture
async def nested_collection_with_items(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int, int], None]:
    """Create parent collection with items and subcollection with items.

    Returns:
        Tuple of (parent_key, parent_item_count, total_item_count)
    """
    # Create parent collection with 5 items
    parent_keys = await test_data_manager.create_test_collections(
        1, name_prefix="Parent Collection"
    )
    parent_key = parent_keys[0]
    parent_items = await test_data_manager.create_test_items(5, parent_key)
    parent_count = len(parent_items)

    # Create subcollection with 3 items
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
    """Create deeply nested collection structure (4 levels) with items at each level.

    Returns:
        Tuple of (root_key, dict mapping level to item count)
    """
    # Create root collection with 2 items
    root_keys = await test_data_manager.create_test_collections(1, name_prefix="Deep Root")
    root_key = root_keys[0]
    root_items = await test_data_manager.create_test_items(2, root_key)

    counts = {"level_0": len(root_items)}

    # Create level 1: 2 subcollections with 3 items each
    level1_keys = await test_data_manager.create_test_collections(
        2, parent_key=root_key, name_prefix="Deep L1"
    )
    level1_count = 0
    for key in level1_keys:
        items = await test_data_manager.create_test_items(3, key)
        level1_count += len(items)
    counts["level_1"] = level1_count

    # Create level 2: 2 subcollections under first L1 collection with 2 items each
    level2_keys = await test_data_manager.create_test_collections(
        2, parent_key=level1_keys[0], name_prefix="Deep L2"
    )
    level2_count = 0
    for key in level2_keys:
        items = await test_data_manager.create_test_items(2, key)
        level2_count += len(items)
    counts["level_2"] = level2_count

    # Create level 3: 1 subcollection under first L2 collection with 1 item
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
    """Create parent with subcollections where some items appear in multiple collections.

    Returns:
        Tuple of (parent_key, unique_item_count, total_appearances)
    """
    # Create parent collection
    parent_keys = await test_data_manager.create_test_collections(1, name_prefix="Duplicate Parent")
    parent_key = parent_keys[0]

    # Create 5 unique items
    unique_items = await test_data_manager.create_test_items(5)

    # Add 3 items to parent collection
    await test_data_manager.add_items_to_collection(unique_items[:3], parent_key)

    # Create 2 subcollections
    sub_keys = await test_data_manager.create_test_collections(
        2, parent_key=parent_key, name_prefix="Duplicate Sub"
    )

    # Add items to subcollections with overlap
    # Sub1: items 0, 1, 2, 3 (items 0,1,2 are duplicates from parent)
    await test_data_manager.add_items_to_collection(unique_items[:4], sub_keys[0])

    # Sub2: items 2, 3, 4 (items 2,3 are duplicates)
    await test_data_manager.add_items_to_collection(unique_items[2:], sub_keys[1])

    # Unique items: 5 total
    # Total appearances: 3 (parent) + 4 (sub1) + 3 (sub2) = 10
    unique_count = 5
    total_appearances = 10

    yield parent_key, unique_count, total_appearances


@pytest.fixture
async def collection_with_empty_subcollections(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create parent collection with items and empty subcollections.

    Returns:
        Tuple of (parent_key, item_count)
    """
    # Create parent collection with 4 items
    parent_keys = await test_data_manager.create_test_collections(1, name_prefix="Empty Sub Parent")
    parent_key = parent_keys[0]
    parent_items = await test_data_manager.create_test_items(4, parent_key)

    # Create 3 empty subcollections
    await test_data_manager.create_test_collections(
        3, parent_key=parent_key, name_prefix="Empty Sub"
    )

    yield parent_key, len(parent_items)


@pytest.fixture
async def large_nested_collection(
    test_data_manager: "ZoteroTestDataManager",
) -> AsyncGenerator[tuple[str, int], None]:
    """Create parent collection with multiple subcollections for chunking tests.

    Returns:
        Tuple of (parent_key, total_item_count)
    """
    # Create parent with 10 items
    parent_keys = await test_data_manager.create_test_collections(1, name_prefix="Large Nested")
    parent_key = parent_keys[0]
    await test_data_manager.create_test_items(10, parent_key)

    # Create 5 subcollections with 8 items each
    sub_keys = await test_data_manager.create_test_collections(
        5, parent_key=parent_key, name_prefix="Large Sub"
    )
    for sub_key in sub_keys:
        await test_data_manager.create_test_items(8, sub_key)

    # Total: 10 (parent) + 5*8 (subs) = 50 items
    total_count = 10 + 5 * 8

    yield parent_key, total_count


# Zotero test instance fixtures


@pytest.fixture(scope="session")
def zotero_test_environment() -> Generator["ZoteroInstance | None", None, None]:
    """Provision an isolated Zotero process for integration tests.

    Activated only when ZOTERO_TEST_INSTANCE=true in environment.
    Yields ZoteroInstance on success, None if not enabled.
    Tests that need a live instance should skip when None.
    """
    from tests.zotero_instance import (
        ZoteroInstance,
        ZoteroInstancePool,
        ZoteroProcessGuard,
        detect_xvfb_needed,
    )

    if os.getenv("ZOTERO_TEST_INSTANCE", "false").lower() != "true":
        yield None
        return

    zotero_bin = Path(os.getenv("ZOTERO_BIN_PATH", "zotero"))
    guard = ZoteroProcessGuard()
    guard.cleanup_stale()

    use_xvfb = detect_xvfb_needed()
    pool = ZoteroInstancePool(
        zotero_bin=zotero_bin,
        guard=guard,
        use_xvfb=use_xvfb,
    )

    instance: ZoteroInstance | None = None
    try:
        instance = pool.acquire()
        yield instance
    finally:
        pool.release_all()


@pytest.fixture(scope="session")
def local_live_client(
    zotero_test_environment: "ZoteroInstance | None",
) -> ZoteroClient | None:
    """ZoteroClient connected to the live local Zotero instance.

    Returns None when ZOTERO_TEST_INSTANCE is not enabled.
    """
    if zotero_test_environment is None:
        return None
    settings = Settings(
        zotero_local=True,
        zotero_port=zotero_test_environment.port,
        zotero_library_id="0",
    )
    return ZoteroClient(settings)
