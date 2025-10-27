import contextlib
import os
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from fastmcp import Context

import src.mcp_server
import src.zotero_client
from src.config import Settings
from src.models import ZoteroItem
from src.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.test_helpers import ZoteroTestDataManager


@pytest.fixture(scope="session", autouse=True)
def load_test_env() -> None:
    """Automatically load .env.test for all tests in the session."""
    # Try to load .env.test if it exists
    env_test_path = os.path.join(os.path.dirname(__file__), "..", ".env.test")
    if os.path.exists(env_test_path):
        load_dotenv(env_test_path)
    else:
        # Fallback to .env.test in current directory
        load_dotenv(".env.test")


@pytest.fixture
def local_settings() -> Settings:
    """Settings for local Zotero mode."""
    return Settings(
        zotero_local=True,
        zotero_library_id="",
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
def local_zotero_client(local_settings: Settings) -> ZoteroClient:
    """Zotero client in local mode."""
    return ZoteroClient(local_settings)


@pytest.fixture
def web_zotero_client(web_settings: Settings) -> ZoteroClient:
    """Zotero client in web mode with mocked API."""
    with patch("src.zotero_client.zotero.Zotero") as mock_zotero:
        mock_zotero.return_value = MagicMock()
        return ZoteroClient(web_settings)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test configuration using real Zotero sandbox."""
    load_dotenv(".env.test")

    # Use either test Zotero account or local SQLite
    return Settings(
        zotero_local=os.getenv("TEST_ZOTERO_LOCAL", "false").lower() == "true",
        zotero_library_id=os.getenv("TEST_ZOTERO_LIBRARY_ID", ""),
        zotero_api_key=os.getenv("TEST_ZOTERO_API_KEY"),
        zotero_library_type=os.getenv("TEST_ZOTERO_LIBRARY_TYPE", "user"),
        max_chunk_size=5000,  # Smaller chunks for testing
        cache_ttl=1,  # Short TTL for testing
    )


@pytest.fixture(scope="session")
async def real_zotero_client(test_settings: Settings) -> AsyncGenerator[ZoteroClient, None]:
    """Real Zotero client for E2E tests."""
    # Create test client and override module singleton
    test_client = ZoteroClient(test_settings)
    original_client = src.zotero_client.zotero_client
    src.zotero_client.zotero_client = test_client

    yield test_client

    # Restore original singleton and clean cache
    src.zotero_client.zotero_client = original_client
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
async def mcp_context() -> Context:
    """Create MCP context for tool testing."""
    from fastmcp import FastMCP

    mcp = FastMCP("test-mcp")
    return Context(mcp)


@pytest.fixture(scope="function")
async def setup_test_data(real_zotero_client: ZoteroClient) -> AsyncGenerator[dict[str, Any], None]:
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
    if created_items and real_zotero_client.mode != "local":
        for item_key in created_items:
            with contextlib.suppress(Exception):
                await real_zotero_client.delete_item_by_key(item_key)


@pytest.fixture(scope="session")
async def test_data_manager(
    real_zotero_client: ZoteroClient,
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

    manager = ZoteroTestDataManager(real_zotero_client)

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
def chunker_with_small_size() -> Generator[int, None, None]:
    """Temporarily set small chunk size for testing chunking behavior.

    Returns:
        The small chunk size (100 tokens)
    """
    original_size = src.mcp_server._chunker.max_tokens
    small_size = 100

    src.mcp_server._chunker.max_tokens = small_size

    yield small_size

    # Restore original size
    src.mcp_server._chunker.max_tokens = original_size


@pytest.fixture
def chunker_with_stress_size() -> Generator[int, None, None]:
    """Temporarily set chunk size for stress testing (5KB).

    Returns:
        The stress test chunk size (5000 tokens)
    """
    original_size = src.mcp_server._chunker.max_tokens
    stress_size = 5000

    src.mcp_server._chunker.max_tokens = stress_size

    yield stress_size

    # Restore original size
    src.mcp_server._chunker.max_tokens = original_size


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
