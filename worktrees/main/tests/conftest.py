import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
from dotenv import load_dotenv
from fastmcp import Context
from pyzotero import zotero

from src.config import Settings
from src.mcp_server import get_client, mcp
from src.zotero_client import ZoteroClient


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


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


@pytest.fixture
async def real_zotero_client(test_settings: Settings) -> AsyncGenerator[ZoteroClient, None]:
    """Real Zotero client for E2E tests."""
    # Override global settings
    import src.config
    src.config.settings = test_settings
    
    client = ZoteroClient()
    yield client
    
    # Clean cache after each test
    client.cache.clear()


@pytest.fixture
async def test_collection_key() -> str:
    """Key of test collection with sample data."""
    # This should be created once in your test Zotero account
    return os.getenv("TEST_COLLECTION_KEY", "TESTCOLL")


@pytest.fixture
async def test_item_with_pdf() -> str:
    """Key of test item that has PDF attachment."""
    return os.getenv("TEST_ITEM_WITH_PDF", "TESTITEM1")


@pytest.fixture
async def test_item_without_pdf() -> str:
    """Key of test item without attachments."""
    return os.getenv("TEST_ITEM_NO_PDF", "TESTITEM2")


@pytest.fixture
async def mcp_context() -> Context:
    """Create MCP context for tool testing."""
    return Context()


@pytest.fixture(scope="function")
async def setup_test_data(real_zotero_client: ZoteroClient) -> AsyncGenerator[dict, None]:
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
    
    # Cleanup: delete created items
    if created_items and not real_zotero_client.mode == "local":
        for item_key in created_items:
            try:
                real_zotero_client.client.delete_item(item_key)
            except Exception:
                pass  # Ignore cleanup errors