"""Tests for ZoteroClientRouter and webonly decorator."""

import pytest

from src.client_router import ZoteroClientRouter
from src.config import Settings
from src.exceptions import WebOnlyOperationError
from src.protocols import webonly


class TestWebOnlyDecorator:
    """Test the @webonly decorator functionality."""

    @pytest.mark.asyncio
    async def test_webonly_blocks_local_mode(self) -> None:
        """Test that @webonly raises error for local mode clients."""

        class MockClient:
            def __init__(self, mode: str):
                self.mode = mode

            @webonly
            async def create_item(self):
                return "created"

        local_client = MockClient("local")
        with pytest.raises(WebOnlyOperationError) as exc_info:
            await local_client.create_item()

        assert "create_item" in str(exc_info.value)
        assert "web API access" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_webonly_allows_web_mode(self) -> None:
        """Test that @webonly allows web mode clients."""

        class MockClient:
            def __init__(self, mode: str):
                self.mode = mode

            @webonly
            async def create_item(self):
                return "created"

        web_client = MockClient("web")
        result = await web_client.create_item()
        assert result == "created"


class TestZoteroClientRouter:
    """Test ZoteroClientRouter functionality."""

    def test_router_initialization_local_mode(self):
        """Test router initialization with local mode."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        assert router.has_local_client or router.has_web_client
        assert router.default_client is not None

    def test_router_mode_detection(self):
        """Test router mode detection."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        # Should be local or hybrid depending on API key availability
        assert router.mode in ["local", "web", "hybrid"]

    def test_router_read_client_preference(self):
        """Test that read_client prefers local when available."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        read_client = router.read_client
        assert read_client is not None

        # If local client exists, it should be preferred
        if router.has_local_client:
            assert read_client.mode == "local"

    def test_router_operation_routing(self):
        """Test router operation-based client selection."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        # Read operations should prefer local
        if router.has_local_client:
            read_client = router.get_client_for_operation("search")
            assert read_client.mode == "local"

        # Write operations require web (if available)
        if router.has_web_client:
            write_client = router.get_client_for_operation("create")
            assert write_client.mode == "web"

    def test_router_representation(self):
        """Test router string representation."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        repr_str = repr(router)
        assert "ZoteroClientRouter" in repr_str
        assert "mode=" in repr_str
        assert "local=" in repr_str
        assert "web=" in repr_str


class TestZoteroClientProtocolImplementation:
    """Test that ZoteroClientRouter correctly implements ZoteroClientProtocol."""

    def test_router_has_protocol_properties(self):
        """Test that router has all required protocol properties."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        # Check required properties exist
        assert hasattr(router, "mode")
        assert hasattr(router, "cache")
        assert hasattr(router, "items")
        assert hasattr(router, "collections")

        # Check property types
        assert isinstance(router.mode, str)
        assert isinstance(router.cache, dict)

    def test_router_has_protocol_methods(self):
        """Test that router has all required protocol methods."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        # Read operation methods
        read_methods = [
            "get_collection",
            "get_item",
            "get_raw_item",
            "get_children",
            "get_fulltext",
            "get_pdf_text",
            "get_all_items",
            "get_item_template",
            "get_collection_items_list",
        ]

        for method_name in read_methods:
            assert hasattr(router, method_name)
            assert callable(getattr(router, method_name))

        # Write operation methods
        write_methods = [
            "create_items",
            "update_item",
            "delete_item",
            "delete_item_by_key",
            "create_collections",
            "delete_collection_by_key",
            "add_to_collection",
        ]

        for method_name in write_methods:
            assert hasattr(router, method_name)
            assert callable(getattr(router, method_name))

    @pytest.mark.asyncio
    async def test_router_protocol_delegation(self):
        """Test that router methods delegate to appropriate clients."""
        settings = Settings(zotero_local=True, zotero_library_id="1")
        router = ZoteroClientRouter(settings=settings)

        # Check that router delegates property access
        if router.has_local_client:
            # Cache should come from read_client
            assert router.cache is router.read_client.cache
