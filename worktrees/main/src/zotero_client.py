from collections.abc import Iterator
from typing import Any, overload

from pyzotero import zotero

from . import config
from .exceptions import ConfigurationError, ZoteroWriteError
from .models import (
    Attachment,
    CollectionCreate,
    ItemCreate,
    ItemUpdate,
    ZoteroCollectionResponse,
    ZoteroItem,
    ZoteroWriteResponse,
)


class ItemsIterator:
    """Lazy iterator for Zotero items with pagination support.

    Supports:
    - Iteration: for item in items: ... (one-time use)
    - Length: len(items) - fetches total count without loading all items
    - All: items.all() - loads all items at once
    """

    def __init__(self, client: zotero.Zotero, fetch_func: Any, batch_size: int = 25):
        """Initialize items iterator.

        Args:
            client: Pyzotero client instance
            fetch_func: Function to call for fetching (e.g., client.items)
            batch_size: Number of items per API request
        """
        self._client = client
        self._fetch_func = fetch_func
        self._batch_size = batch_size

    def __len__(self) -> int:
        """Get total count of items without loading all of them."""
        # Fetch just one item to get total count from headers
        self._fetch_func(limit=1)
        # Pyzotero stores last response count in request headers
        return int(self._client.request.headers["Total-Results"])

    def __iter__(self) -> Iterator[ZoteroItem]:
        """Iterate over all items, fetching in batches as needed.

        Note: Iterator is one-time use. Create new ItemsIterator for re-iteration.
        """
        # First batch establishes the pagination links
        first_batch = self._fetch_func(limit=self._batch_size)
        yield from (ZoteroItem.model_validate(i) for i in first_batch)

        # Use pyzotero's makeiter for remaining pages
        for batch in self._client.makeiter(self._fetch_func):
            yield from batch

    def all(self) -> list[ZoteroItem]:
        """Fetch all items at once using everything()."""
        result: list[dict[str, Any]] = self._client.everything(self._fetch_func())
        return [ZoteroItem.model_validate(i) for i in result]

    def keys(self) -> list[str]:
        """Get all item keys (efficient - loads all items)."""
        return [item.key for item in self.all()]


class Collection:
    """Represents a Zotero collection with lazy-loaded items."""

    def __init__(self, client: zotero.Zotero, data: dict[str, Any]):
        """Initialize collection.

        Args:
            client: Pyzotero client instance
            data: Collection data from API
        """
        self._client = client
        # Validate incoming data with Pydantic
        self._validated_data = ZoteroCollectionResponse.model_validate(data)
        self._data = data  # Keep raw data for pyzotero compatibility
        self._items: ItemsIterator | None = None
        self._subcollections: list[Collection] | None = None

    @property
    def key(self) -> str:
        """Collection key."""
        return self._validated_data.key

    @property
    def name(self) -> str:
        """Collection name."""
        return self._validated_data.data.name

    @property
    def version(self) -> int:
        """Collection version."""
        return self._validated_data.version

    @property
    def items(self) -> ItemsIterator:
        """Lazy iterator over items in this collection."""
        if self._items is None:
            self._items = ItemsIterator(
                self._client, lambda **kwargs: self._client.collection_items(self.key, **kwargs)
            )
        return self._items

    @property
    def subcollections(self) -> list["Collection"]:
        """Get subcollections (loaded once)."""
        if self._subcollections is None:
            subcoll_data = self._client.collections_sub(self.key)
            self._subcollections = [Collection(self._client, data) for data in subcoll_data]
        return self._subcollections

    def delete(self) -> None:
        """Delete this collection."""
        self._client.delete_collection(self._data)

    def __repr__(self) -> str:
        return f"Collection(key={self.key!r}, name={self.name!r})"


class ZoteroClient:
    """Simplified client supporting both local and web access."""

    def __init__(self, settings: config.Settings | None = None) -> None:
        """Initialize ZoteroClient with optional settings for testing.

        Args:
            settings: Optional Settings instance. If None, uses config.settings singleton.
        """
        self.settings = settings or config.settings

        if self.settings.zotero_local:
            self.mode = "local"
            self._client = self._init_local_client()
        else:
            self.mode = "web"
            self._client = self._init_web_client()

        self.cache: dict[str, Any] = {}  # Simple in-memory cache
        self._items: ItemsIterator | None = None
        self._collections: list[Collection] | None = None

    def _init_web_client(self) -> zotero.Zotero:
        """Initialize web Zotero client using remote API."""
        library_id = self.settings.zotero_library_id
        api_key = self.settings.zotero_api_key
        library_type = self.settings.zotero_library_type

        if not library_id or not api_key:
            raise ConfigurationError("ZOTERO_LIBRARY_ID and ZOTERO_API_KEY required")

        return zotero.Zotero(library_id, library_type, api_key, local=False)

    def _init_local_client(self) -> zotero.Zotero:
        """Initialize local Zotero client using local HTTP server.

        Requires Zotero 7+ with local API server enabled.
        Endpoint: http://localhost:23119/api
        Note: Only read operations are supported in local mode.
        """
        library_id = self.settings.zotero_library_id or "1"  # Dummy ID for local mode
        library_type = self.settings.zotero_library_type

        return zotero.Zotero(library_id, library_type, local=True)

    @property
    def items(self) -> ItemsIterator:
        """Lazy iterator over all items in library.

        Usage:
            # Get count without loading all items
            count = len(client.items)

            # Iterate (lazy - fetches in batches)
            for item in client.items:
                print(item['data']['title'])

            # Get all at once
            all_items = client.items.all()

            # Get just keys
            keys = client.items.keys()
        """
        if self._items is None:
            self._items = ItemsIterator(self._client, lambda **kwargs: self._client.items(**kwargs))
        return self._items

    @property
    def collections(self) -> list[Collection]:
        """Get all collections (with pagination support).

        Usage:
            for collection in client.collections:
                print(f"{collection.name}: {len(collection.items)} items")
        """
        if self._collections is None:
            # Fetch all collections using everything()
            colls_data = self._client.everything(self._client.collections())
            self._collections = [Collection(self._client, data) for data in colls_data]
        return self._collections

    @overload
    async def get_collection(self, *, name: str) -> Collection | None: ...

    @overload
    async def get_collection(self, *, key: str) -> Collection: ...

    async def get_collection(
        self, name: str | None = None, *, key: str | None = None
    ) -> Collection | None:
        """Get collection by name or key.

        Args:
            name: Collection name to search for (returns None if not found)
            key: Collection key (use as keyword argument: key='ABC123')

        Returns:
            Collection object or None if searching by name and not found

        Usage:
            # By name
            collection = client.get_collection("My Articles")

            # By key
            collection = client.get_collection(key='ABC123')
        """
        if key is not None:
            data = self._client.collection(key)
            return Collection(self._client, data)
        elif name is not None:
            for collection in self.collections:
                if collection.name == name:
                    return collection
        return None

    async def get_fulltext(self, item_key: str) -> str | None:
        """Get full text content if available."""
        cache_key = f"fulltext:{item_key}"

        if cache_key in self.cache:
            cached_value = self.cache[cache_key]
            if isinstance(cached_value, str):
                return cached_value
            return None

        try:
            # Use pyzotero's fulltext_item() method
            fulltext_data = self._client.fulltext_item(item_key)

            # Extract content from response
            content = fulltext_data.get("content")

            if content:
                self.cache[cache_key] = content
                return str(content)

        except Exception:
            # Item may not have fulltext available
            # Cache the failure to avoid repeated API calls
            self.cache[cache_key] = None
            # Don't raise here - return None to indicate no content available
            # Callers should check for None and raise ContentNotAvailableError if needed
            pass

        return None

    async def get_item(self, item_key: str) -> ZoteroItem:
        """Get single item by key."""
        raw_item = self._client.item(item_key)
        return ZoteroItem.model_validate(raw_item)

    async def get_raw_item(self, item_key: str) -> dict[str, Any]:
        """Get raw item data as dict.

        Args:
            item_key: Item key

        Returns:
            Raw item dict from API
        """
        raw_item: dict[str, Any] = self._client.item(item_key)
        return raw_item

    async def delete_item(self, item: ZoteroItem) -> None:
        """Delete item using ZoteroItem model."""
        # Convert to dict for pyzotero API (needs key + version)
        self._client.delete_item(item.model_dump(mode="json"))

    async def delete_item_by_key(self, item_key: str) -> None:
        """Delete item by key string.

        Args:
            item_key: Item key to delete
        """
        # Need to fetch full item to get version
        raw_item = self._client.item(item_key)
        self._client.delete_item(raw_item)

    async def delete_collection_by_key(self, collection_key: str) -> None:
        """Delete collection by key.

        Args:
            collection_key: Collection key to delete
        """
        # Need to fetch full collection to get version
        raw_coll = self._client.collection(collection_key)
        self._client.delete_collection(raw_coll)

    async def create_items(self, items: list[ItemCreate]) -> list[ZoteroItem]:
        """Create new items in Zotero library.

        Args:
            items: List of item creation data

        Returns:
            List of created items as ZoteroItem models

        Raises:
            ZoteroWriteError: If any items failed to create
        """
        items_data = [item.model_dump(exclude_none=True) for item in items]
        raw_response = self._client.create_items(items_data)

        # Validate response structure
        response = ZoteroWriteResponse.model_validate(raw_response)

        # Check for failures
        if response.has_failures():
            raise ZoteroWriteError("create_items", response.failed)

        # Extract successful items and validate with Pydantic
        successful_items = response.get_successful_objects()
        return [ZoteroItem.model_validate(item_dict) for item_dict in successful_items]

    async def get_children(self, item_key: str) -> list[Attachment]:
        """Get child attachments for an item.

        Args:
            item_key: Parent item key

        Returns:
            List of attachments
        """
        children_data = self._client.children(item_key)
        return [
            Attachment(
                key=child["key"],
                item_type=child["data"]["itemType"],
                content_type=child["data"].get("contentType"),
                filename=child["data"].get("filename"),
                data=child["data"],
            )
            for child in children_data
        ]

    async def update_item(self, item_key: str, update: ItemUpdate) -> None:
        """Update an existing item.

        Args:
            item_key: Item key to update
            update: Update data
        """
        item_dict = self._client.item(item_key)
        update_data = update.model_dump(exclude_none=True)

        # Merge update data into item
        for key, value in update_data.items():
            item_dict["data"][key] = value

        self._client.update_item(item_dict)

    async def get_all_items(self) -> list[dict[str, Any]]:
        """Get all items in library as raw dicts.

        Returns:
            List of all items (raw API format)
        """
        return list(self._client.items())

    async def get_item_template(self, template_type: str) -> dict[str, Any]:
        """Get item template for creating new items.

        Args:
            template_type: Type of item (e.g., 'book', 'journalArticle')

        Returns:
            Template dict with default fields
        """
        template: dict[str, Any] = self._client.item_template(template_type)
        return template

    async def create_collections(self, collections: list[CollectionCreate]) -> list[Collection]:
        """Create new collections.

        Args:
            collections: List of collection creation data

        Returns:
            List of created collections

        Raises:
            ZoteroWriteError: If any collections failed to create
        """
        collections_data = [
            {"name": c.name, "parentCollection": c.parent_collection} for c in collections
        ]
        raw_response = self._client.create_collections(collections_data)

        # Validate response structure
        response = ZoteroWriteResponse.model_validate(raw_response)

        # Check for failures
        if response.has_failures():
            raise ZoteroWriteError("create_collections", response.failed)

        # Extract successful collections and wrap in Collection objects
        successful_colls = response.get_successful_objects()
        # Validate each collection response before wrapping
        validated_colls = [
            ZoteroCollectionResponse.model_validate(coll) for coll in successful_colls
        ]
        return [Collection(self._client, coll.model_dump(mode="json")) for coll in validated_colls]

    async def add_to_collection(self, collection_key: str, items: list[ZoteroItem]) -> None:
        """Add items to a collection.

        Args:
            collection_key: Collection key
            item_keys: List of items keys to add
        """
        for item in items:
            self._client.addto_collection(collection_key, item.model_dump())

    async def get_collection_items_list(self, collection_key: str) -> list[dict[str, Any]]:
        """Get all items in a collection as list.

        Args:
            collection_key: Collection key

        Returns:
            List of items (raw API format)
        """
        items: list[dict[str, Any]] = list(self._client.collection_items(collection_key))
        return items


# Module-level singleton - initialized at import time
zotero_client = ZoteroClient()
