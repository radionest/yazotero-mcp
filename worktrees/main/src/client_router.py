"""Router for choosing between local and web Zotero clients.

This module provides intelligent routing between local and web API clients
based on operation type and availability.
"""

from . import config
from .exceptions import ConfigurationError
from .zotero_client import ZoteroClient


class ZoteroClientRouter:
    """Smart router for selecting appropriate Zotero client.

    Strategy:
    - Read operations: Prefer local (faster, no rate limits)
    - Write operations: Always use web (local is read-only)
    - Fallback: If local unavailable, use web for all operations
    """

    def __init__(self, settings: config.Settings | None = None) -> None:
        """Initialize router with optional settings.

        Args:
            settings: Optional Settings instance. If None, uses config.settings singleton.
        """
        self.settings = settings or config.settings
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
                    zotero_library_id=self.settings.zotero_library_id or "1",
                    zotero_library_type=self.settings.zotero_library_type,
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

    def get_client_for_operation(self, operation: str) -> ZoteroClient:
        """Get appropriate client based on operation type.

        Args:
            operation: Operation name (e.g., 'read', 'write', 'search')

        Returns:
            Appropriate ZoteroClient instance

        Examples:
            >>> router = ZoteroClientRouter()
            >>> # Read operations use local if available
            >>> client = router.get_client_for_operation('search')
            >>> # Write operations always use web
            >>> client = router.get_client_for_operation('create')
        """
        # Write operations require web client
        write_operations = {
            "create",
            "update",
            "delete",
            "add_to_collection",
            "create_items",
            "create_collections",
            "update_item",
            "delete_item",
            "delete_collection",
        }

        if any(op in operation.lower() for op in write_operations):
            return self.write_client

        # Read operations prefer local client
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


# Module-level singleton router
client_router = ZoteroClientRouter()
