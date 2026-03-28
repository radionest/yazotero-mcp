"""Router for choosing between local and web Zotero clients.

This module provides intelligent routing between local and web API clients
based on operation type and availability.
"""

from typing import TYPE_CHECKING, Any, overload

from . import config
from .exceptions import ConfigurationError
from .protocols import ZoteroClientProtocol
from .zotero_client import ZoteroClient

if TYPE_CHECKING:
    from .models import (
        Attachment,
        CollectionCreate,
        ItemCreate,
        ItemUpdate,
        ZoteroCollectionBase,
        ZoteroItem,
        ZoteroSearchParams,
    )


class ZoteroClientRouter(ZoteroClientProtocol):
    """Smart router implementing ZoteroClientProtocol.

    Provides intelligent routing between local and web Zotero clients with
    automatic fallback support. Implements the full ZoteroClientProtocol interface
    by delegating to the appropriate underlying client.

    Strategy:
    - Read operations: Prefer local (faster, no rate limits) with fallback to web
    - Write operations: Always use web (local is read-only)
    - Fallback: Automatically tries web client if local operation fails
    """

    def __init__(self, settings: config.Settings) -> None:
        """Initialize router with settings.

        Args:
            settings: Settings instance for Zotero configuration.
        """
        self.settings = settings
        self._local_client: ZoteroClient | None = None
        self._web_client: ZoteroClient | None = None

        # Initialize clients based on configuration
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize available clients based on configuration."""
        # Try to initialize local client if enabled
        if self.settings.zotero_local:
            try:
                local_settings = config.Settings(
                    zotero_local=True,
                    zotero_library_id=self.settings.zotero_library_id or "0",
                    zotero_library_type=self.settings.zotero_library_type,
                    zotero_port=self.settings.zotero_port,
                )
                self._local_client = ZoteroClient(settings=local_settings)
            except Exception:
                # Local client initialization failed, will fallback to web
                self._local_client = None

        # Try to initialize web client if credentials are available
        if self.settings.zotero_api_key and self.settings.zotero_library_id:
            try:
                web_settings = config.Settings(
                    zotero_local=False,
                    zotero_library_id=self.settings.zotero_library_id,
                    zotero_api_key=self.settings.zotero_api_key,
                    zotero_library_type=self.settings.zotero_library_type,
                )
                self._web_client = ZoteroClient(settings=web_settings)
            except ConfigurationError:
                # Web client requires proper credentials
                self._web_client = None

        # Ensure at least one client is available
        if not self._local_client and not self._web_client:
            raise ConfigurationError(
                "No Zotero client available. "
                "Either enable local mode (ZOTERO_LOCAL=true) with Zotero 7+ running, "
                "or provide web API credentials (ZOTERO_API_KEY and ZOTERO_LIBRARY_ID)."
            )

    @property
    def read_client(self) -> ZoteroClient:
        """Get client optimized for read operations.

        Returns local client if available (faster), otherwise web client.

        Returns:
            ZoteroClient instance for read operations

        Raises:
            ConfigurationError: If no client is available
        """
        if self._local_client:
            return self._local_client
        elif self._web_client:
            return self._web_client
        else:
            raise ConfigurationError("No Zotero client available for read operations")

    @property
    def write_client(self) -> ZoteroClient:
        """Get client for write operations.

        Always returns web client as local API is read-only.

        Returns:
            ZoteroClient instance for write operations

        Raises:
            ConfigurationError: If web client is not configured
        """
        if self._web_client:
            return self._web_client
        else:
            raise ConfigurationError(
                "Write operations require web API. "
                "Please configure ZOTERO_API_KEY and ZOTERO_LIBRARY_ID."
            )

    @property
    def default_client(self) -> ZoteroClient:
        """Get default client for general use.

        Prefers local client for better performance, falls back to web.

        Returns:
            ZoteroClient instance
        """
        return self.read_client

    @property
    def has_local_client(self) -> bool:
        """Check if local client is available."""
        return self._local_client is not None

    @property
    def has_web_client(self) -> bool:
        """Check if web client is available."""
        return self._web_client is not None

    @property
    def mode(self) -> str:
        """Get current routing mode.

        Returns:
            "local" if local client is preferred
            "web" if only web client is available
            "hybrid" if both clients are available
        """
        if self._local_client and self._web_client:
            return "hybrid"
        elif self._local_client:
            return "local"
        else:
            return "web"

    def __repr__(self) -> str:
        return (
            f"ZoteroClientRouter(mode={self.mode!r}, "
            f"local={self.has_local_client}, web={self.has_web_client})"
        )

    # Protocol implementation - delegate to appropriate client
    @property
    def cache(self) -> dict[str, Any]:
        """Access cache from read client."""
        return self.read_client.cache

    async def get_items(self) -> list["ZoteroItem"]:
        """Fetch all items (uses read client)."""
        return await self.read_client.get_items()

    async def get_collections(self) -> list["ZoteroCollectionBase"]:
        """Fetch all collections (uses read client)."""
        return await self.read_client.get_collections()

    # Read operations (support local and web)

    @overload
    async def get_collection(self, *, name: str) -> "ZoteroCollectionBase | None": ...

    @overload
    async def get_collection(self, *, key: str) -> "ZoteroCollectionBase": ...

    async def get_collection(
        self, name: str | None = None, *, key: str | None = None
    ) -> "ZoteroCollectionBase | None":
        """Get collection by name or key (read operation with fallback)."""
        match key, name:
            case None, None:
                raise ValueError("Either name or key must be provided to get_collection")
            case str(), None:
                try:
                    return await self.read_client.get_collection(key=key)
                except Exception as e:
                    if self._local_client and self._web_client:
                        return await self._web_client.get_collection(key=key)
                    raise e
            case None, str():
                try:
                    return await self.read_client.get_collection(name=name)
                except Exception as e:
                    if self._local_client and self._web_client:
                        return await self._web_client.get_collection(name=name)
                    raise e
            case str(), str():
                raise ValueError("Provide either name or key, not both, to get_collection")
            case _:
                raise ValueError("Invalid arguments to get_collection")

    async def get_item(self, item_key: str) -> "ZoteroItem":
        """Get single item by key (read operation with fallback)."""
        try:
            return await self.read_client.get_item(item_key)
        except Exception:
            if self._local_client and self._web_client:
                return await self._web_client.get_item(item_key)
            raise

    async def get_raw_item(self, item_key: str) -> dict[str, Any]:
        """Get raw item data (read operation with fallback)."""
        try:
            return await self.read_client.get_raw_item(item_key)
        except Exception:
            if self._local_client and self._web_client:
                return await self._web_client.get_raw_item(item_key)
            raise

    async def get_children(self, item_key: str) -> list["Attachment"]:
        """Get child attachments (read operation with fallback)."""
        try:
            return await self.read_client.get_children(item_key)
        except Exception:
            if self._local_client and self._web_client:
                return await self._web_client.get_children(item_key)
            raise

    async def get_fulltext(self, item_key: str) -> str | None:
        """Get fulltext with fallback from local to web."""
        try:
            result = await self.read_client.get_fulltext(item_key)
            if result:
                return result
        except Exception:
            pass

        # Fallback to web if local failed or returned None
        if self._local_client and self._web_client:
            return await self._web_client.get_fulltext(item_key)

        return None

    async def get_pdf_text(self, item_key: str) -> str | None:
        """Get PDF text with fallback from local to web."""
        try:
            result = await self.read_client.get_pdf_text(item_key)
            if result:
                return result
        except Exception:
            pass

        # Fallback to web if local failed or returned None
        if self._local_client and self._web_client:
            return await self._web_client.get_pdf_text(item_key)

        return None

    async def search_items(self, search_params: "ZoteroSearchParams") -> list["ZoteroItem"]:
        """Search items across library (read operation with fallback)."""
        try:
            return await self.read_client.search_items(search_params)
        except Exception:
            if self._local_client and self._web_client:
                return await self._web_client.search_items(search_params)
            raise

    async def search_collection_items(
        self, collection_key: str, search_params: "ZoteroSearchParams"
    ) -> list["ZoteroItem"]:
        """Search items within collection (read operation with fallback)."""
        try:
            return await self.read_client.search_collection_items(collection_key, search_params)
        except Exception:
            if self._local_client and self._web_client:
                return await self._web_client.search_collection_items(collection_key, search_params)
            raise

    # Write operations - always use write_client (web)
    async def create_items(self, items: list["ItemCreate"]) -> list["ZoteroItem"]:
        """Create items (write operation - web only)."""
        return await self.write_client.create_items(items)

    async def update_item(self, item_key: str, update: "ItemUpdate") -> None:
        """Update item (write operation - web only)."""
        await self.write_client.update_item(item_key, update)

    async def delete_item(self, item: "ZoteroItem") -> None:
        """Delete item (write operation - web only)."""
        await self.write_client.delete_item(item)

    async def delete_item_by_key(self, item_key: str) -> None:
        """Delete item by key (write operation - web only)."""
        await self.write_client.delete_item_by_key(item_key)

    async def create_collections(
        self, collections: list["CollectionCreate"]
    ) -> list["ZoteroCollectionBase"]:
        """Create collections (write operation - web only)."""
        return await self.write_client.create_collections(collections)

    async def delete_collection_by_key(self, collection_key: str) -> None:
        """Delete collection (write operation - web only)."""
        await self.write_client.delete_collection_by_key(collection_key)

    async def add_to_collection(self, collection_key: str, items: list["ZoteroItem"]) -> None:
        """Add items to collection (write operation - web only)."""
        await self.write_client.add_to_collection(collection_key, items)

    async def remove_from_collection(self, collection_key: str, item_key: str) -> None:
        """Remove item from collection (write operation - web only)."""
        await self.write_client.remove_from_collection(collection_key, item_key)
