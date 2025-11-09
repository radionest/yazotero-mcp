"""Protocol decorators and utilities for Zotero client operations.

This module provides decorators that enforce API compatibility rules,
particularly for operations that are only supported by the web API.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, Protocol, overload

from src.models import Attachment, CollectionCreate, ItemCreate, ItemUpdate, ZoteroItem
from src.zotero_client import Collection, ItemsIterator

from .exceptions import WebOnlyOperationError

# Type variable for generic function signatures


def webonly[F: Callable[..., Any]](func: F) -> F:
    """Decorator to mark methods that require web API access.

    The local Zotero API (http://localhost:23119/api) is read-only and does
    not support write operations. This decorator ensures that methods marked
    with @webonly will raise WebOnlyOperationError when called on a client
    configured for local mode.

    The decorator checks the 'mode' attribute of the first argument (self),
    which should be a ZoteroClient instance.

    Usage:
        class ZoteroClient:
            def __init__(self):
                self.mode = "local"  # or "web"

            @webonly
            async def create_items(self, items):
                # This will raise if self.mode == "local"
                ...

    Raises:
        WebOnlyOperationError: If called on a local mode client

    Args:
        func: The method to decorate (should be a method of ZoteroClient)

    Returns:
        Decorated method that checks client mode before execution
    """

    @wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Check if client is in local mode
        if hasattr(self, "mode") and self.mode == "local":
            raise WebOnlyOperationError(func.__name__)

        # Execute original method
        return await func(self, *args, **kwargs)

    return wrapper  # type: ignore


class ZoteroClientProtocol(Protocol):
    """Protocol defining the interface for Zotero clients.

    This protocol is implemented by both ZoteroClient and ZoteroClientRouter,
    ensuring they provide a consistent API for Zotero operations.

    Implementations must support both read and write operations, though some
    implementations may restrict write operations (e.g., local-only clients).
    """

    # Properties
    @property
    def mode(self) -> str:
        """Client mode: 'local', 'web', or 'hybrid'."""
        ...

    @property
    def cache(self) -> dict[str, Any]:
        """In-memory cache for API responses."""
        ...

    @property
    def items(self) -> "ItemsIterator":
        """Lazy iterator over all items in library."""
        ...

    @property
    def collections(self) -> list["Collection"]:
        """Get all collections with pagination support."""
        ...

    # Read operations (support local and web)
    @overload
    async def get_collection(self, *, name: str) -> Collection | None: ...

    @overload
    async def get_collection(self, *, key: str) -> Collection: ...

    async def get_collection(
        self, name: str | None = None, *, key: str | None = None
    ) -> Collection | None:
        """Get collection by name or key."""
        ...

    async def get_item(self, item_key: str) -> "ZoteroItem":
        """Get single item by key."""
        ...

    async def get_raw_item(self, item_key: str) -> dict[str, Any]:
        """Get raw item data as dict."""
        ...

    async def get_children(self, item_key: str) -> list["Attachment"]:
        """Get child attachments for an item."""
        ...

    async def get_fulltext(self, item_key: str) -> str | None:
        """Get full text content from Zotero's indexed fulltext API."""
        ...

    async def get_pdf_text(self, item_key: str) -> str | None:
        """Get text by downloading and parsing PDF directly."""
        ...

    async def get_all_items(self) -> list[dict[str, Any]]:
        """Get all items in library as raw dicts."""
        ...

    async def get_item_template(self, template_type: str) -> dict[str, Any]:
        """Get item template for creating new items."""
        ...

    async def get_collection_items_list(self, collection_key: str) -> list[dict[str, Any]]:
        """Get all items in a collection as list."""
        ...

    # Write operations (require web API)
    async def create_items(self, items: list["ItemCreate"]) -> list["ZoteroItem"]:
        """Create new items in Zotero library."""
        ...

    async def update_item(self, item_key: str, update: "ItemUpdate") -> None:
        """Update an existing item."""
        ...

    async def delete_item(self, item: "ZoteroItem") -> None:
        """Delete item using ZoteroItem model."""
        ...

    async def delete_item_by_key(self, item_key: str) -> None:
        """Delete item by key string."""
        ...

    async def create_collections(self, collections: list["CollectionCreate"]) -> list["Collection"]:
        """Create new collections."""
        ...

    async def delete_collection_by_key(self, collection_key: str) -> None:
        """Delete collection by key."""
        ...

    async def add_to_collection(self, collection_key: str, items: list["ZoteroItem"]) -> None:
        """Add items to a collection."""
        ...
