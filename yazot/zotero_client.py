import asyncio
import logging
from collections.abc import Callable
from typing import Any, overload

from pyzotero import zotero, zotero_errors

from . import config
from .exceptions import ConfigurationError, ZoteroError, ZoteroNotFoundError, ZoteroWriteError
from .models import (
    Attachment,
    CollectionCreate,
    ItemCreate,
    ItemUpdate,
    ZoteroCollectionBase,
    ZoteroCollectionResponse,
    ZoteroItem,
    ZoteroSearchParams,
    ZoteroWriteResponse,
)
from .protocols import ZoteroClientProtocol, webonly

logger = logging.getLogger(__name__)


async def _run_sync[T](func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a synchronous function in a thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


class Collection(ZoteroCollectionBase):
    """Represents a Zotero collection with async item access."""

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
    def num_items(self) -> int:
        """Number of items in collection."""
        return self._validated_data.meta.num_items

    @property
    def parent_collection(self) -> str | bool | None:
        """Parent collection key, or False if top-level."""
        return self._validated_data.data.parent_collection

    async def get_items(self) -> list[ZoteroItem]:
        """Fetch all items in this collection."""
        raw_items = await _run_sync(
            lambda: self._client.everything(self._client.collection_items_top(self.key))
        )
        return [ZoteroItem.model_validate(i) for i in raw_items]

    async def get_subcollections(self) -> list[ZoteroCollectionBase]:
        """Fetch subcollections of this collection."""
        subcoll_data = await _run_sync(self._client.collections_sub, self.key)
        return [Collection(self._client, data) for data in subcoll_data]

    async def delete(self) -> None:
        """Delete this collection."""
        await _run_sync(self._client.delete_collection, self._data)

    def __repr__(self) -> str:
        return f"Collection(key={self.key!r}, name={self.name!r})"


class ZoteroClient(ZoteroClientProtocol):
    """Simplified client supporting both local and web access."""

    def __init__(self, settings: config.Settings) -> None:
        """Initialize ZoteroClient with settings.

        Args:
            settings: Settings instance for Zotero configuration.
        """
        self.settings = settings

        if self.settings.zotero_local:
            self._mode = "local"
            self._client = self._init_local_client()
        else:
            self._mode = "web"
            self._client = self._init_web_client()

        self._cache: dict[str, Any] = {}  # Simple in-memory cache

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def cache(self) -> dict[str, Any]:
        return self._cache

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
        Port configurable via ZOTERO_PORT (default: 23119).
        Note: Only read operations are supported in local mode.
        """
        library_id = self.settings.zotero_library_id or "0"  # Dummy ID for local mode
        library_type = self.settings.zotero_library_type

        client = zotero.Zotero(library_id, library_type, local=True)
        if self.settings.zotero_port != 23119:
            client.endpoint = f"http://localhost:{self.settings.zotero_port}/api"
        return client

    async def get_item_template(self, item_type: str) -> dict[str, Any]:
        """Get item creation template from Zotero API.

        Returns raw dict — pyzotero returns untyped templates per item type.
        """
        result: dict[str, Any] = await _run_sync(self._client.item_template, item_type)
        return result

    async def get_items(self) -> list[ZoteroItem]:
        """Fetch all top-level items in library (excludes attachments/notes)."""
        try:
            raw_items = await _run_sync(lambda: self._client.everything(self._client.top()))
            return [ZoteroItem.model_validate(i) for i in raw_items]
        except zotero_errors.UserNotAuthorisedError as e:
            raise ZoteroError(
                "Access denied when fetching items. "
                "Hint: check that ZOTERO_API_KEY has read permissions."
            ) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Zotero API error when fetching items: {e}. "
                "Hint: verify Zotero is running and accessible."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error fetching items: {type(e).__name__}: {e}. "
                "Hint: check network connectivity and Zotero availability."
            ) from e

    async def get_collections(self) -> list[ZoteroCollectionBase]:
        """Fetch all collections with pagination support."""
        try:
            colls_data = await _run_sync(
                lambda: self._client.everything(self._client.collections())
            )
            return [Collection(self._client, data) for data in colls_data]
        except zotero_errors.UserNotAuthorisedError as e:
            raise ZoteroError(
                "Access denied when fetching collections. "
                "Hint: check that ZOTERO_API_KEY has read permissions."
            ) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Zotero API error when fetching collections: {e}. "
                "Hint: verify Zotero is running and accessible."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error fetching collections: {type(e).__name__}: {e}. "
                "Hint: check network connectivity and Zotero availability."
            ) from e

    @overload
    async def get_collection(self, *, name: str) -> ZoteroCollectionBase | None: ...

    @overload
    async def get_collection(self, *, key: str) -> ZoteroCollectionBase: ...

    async def get_collection(
        self, name: str | None = None, *, key: str | None = None
    ) -> ZoteroCollectionBase | None:
        """Get collection by name or key.

        Args:
            name: Collection name to search for (returns None if not found)
            key: Collection key (use as keyword argument: key='ABC123')
        """
        if key is not None:
            try:
                data = await _run_sync(self._client.collection, key)
                return Collection(self._client, data)
            except zotero_errors.ResourceNotFoundError as e:
                raise ZoteroNotFoundError("collection", key) from e
            except zotero_errors.PyZoteroError as e:
                raise ZoteroError(
                    f"Zotero API error when fetching collection '{key}': {e}. "
                    "Hint: verify the collection key is correct."
                ) from e
            except Exception as e:
                raise ZoteroError(
                    f"Unexpected error fetching collection '{key}': {type(e).__name__}: {e}. "
                    "Hint: check network connectivity and Zotero availability."
                ) from e
        elif name is not None:
            for collection in await self.get_collections():
                if collection.name == name:
                    return collection
        return None

    async def _find_pdf_attachment_key(self, item_key: str) -> str | None:
        """Find PDF attachment key: check if item itself is PDF, otherwise search children.

        Args:
            item_key: Item key (can be parent item or attachment itself)

        Returns:
            PDF attachment key, or None if no PDF found
        """
        # Check if item itself is a PDF attachment
        try:
            raw_item = await _run_sync(self._client.item, item_key)
            item_data = raw_item.get("data", {})
            if (
                item_data.get("itemType") == "attachment"
                and item_data.get("contentType") == "application/pdf"
            ):
                return item_key
        except Exception:
            pass

        # Otherwise search children for PDF attachment
        children = await self.get_children(item_key)
        for child in children:
            if child.content_type == "application/pdf":
                return child.key

        return None

    async def get_fulltext(self, item_key: str) -> str | None:
        """Get full text content from PDF attachment of an item.

        Args:
            item_key: Item key (parent item or PDF attachment itself)

        Returns:
            Full text content from PDF attachment, or None if not available
        """
        cache_key = f"fulltext:{item_key}"

        if cache_key in self.cache:
            cached_value = self.cache[cache_key]
            if isinstance(cached_value, str):
                return cached_value
            return None

        try:
            pdf_key = await self._find_pdf_attachment_key(item_key)

            if not pdf_key:
                self._cache[cache_key] = None
                return None

            fulltext_data = await _run_sync(self._client.fulltext_item, pdf_key)
            content = fulltext_data.get("content")

            if content:
                self._cache[cache_key] = content
                return str(content)

        except (zotero_errors.ResourceNotFoundError, KeyError, ValueError):
            # No fulltext available for this item — safe to cache
            self._cache[cache_key] = None
            return None
        except Exception:
            # Transient error (network, timeout) — do NOT cache, allow retry
            logger.warning("Failed to get fulltext for item %s", item_key, exc_info=True)

        return None

    async def get_pdf_text(self, item_key: str) -> str | None:
        """Get text content by downloading and parsing PDF file directly.

        Args:
            item_key: Item key (parent item or PDF attachment itself)

        Returns:
            Extracted text content from PDF, or None if not available
        """
        cache_key = f"pdf_text:{item_key}"

        if cache_key in self.cache:
            cached_value = self.cache[cache_key]
            if isinstance(cached_value, str):
                return cached_value
            return None

        try:
            pdf_key = await self._find_pdf_attachment_key(item_key)

            if not pdf_key:
                self._cache[cache_key] = None
                return None

            pdf_bytes = await _run_sync(self._client.file, pdf_key)

            import io

            from pypdf import PdfReader

            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)

            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            full_text = "\n\n".join(text_parts)

            if full_text:
                self._cache[cache_key] = full_text
                return full_text

        except (zotero_errors.ResourceNotFoundError, KeyError, ValueError):
            # No PDF available for this item — safe to cache
            self._cache[cache_key] = None
            return None
        except Exception:
            # Transient error (network, PDF parsing) — do NOT cache, allow retry
            logger.warning("Failed to get PDF text for item %s", item_key, exc_info=True)

        return None

    async def get_item(self, item_key: str) -> ZoteroItem:
        """Get single item by key."""
        try:
            raw_item = await _run_sync(self._client.item, item_key)
            return ZoteroItem.model_validate(raw_item)
        except zotero_errors.ResourceNotFoundError as e:
            raise ZoteroNotFoundError("item", item_key) from e
        except zotero_errors.UserNotAuthorisedError as e:
            raise ZoteroError(
                f"Access denied when fetching item '{item_key}'. "
                "Hint: check that ZOTERO_API_KEY has read permissions."
            ) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Zotero API error when fetching item '{item_key}': {e}. "
                "Hint: verify Zotero is running and accessible."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error fetching item '{item_key}': {type(e).__name__}: {e}. "
                "Hint: check network connectivity and Zotero availability."
            ) from e

    async def get_raw_item(self, item_key: str) -> dict[str, Any]:
        """Get raw item data as dict."""
        try:
            raw_item: dict[str, Any] = await _run_sync(self._client.item, item_key)
            return raw_item
        except zotero_errors.ResourceNotFoundError as e:
            raise ZoteroNotFoundError("item", item_key) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Zotero API error when fetching item '{item_key}': {e}. "
                "Hint: verify the item key is correct and Zotero is accessible."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error fetching item '{item_key}': {type(e).__name__}: {e}. "
                "Hint: check network connectivity and Zotero availability."
            ) from e

    @webonly
    async def delete_item(self, item: ZoteroItem) -> None:
        """Delete item using ZoteroItem model."""
        await _run_sync(self._client.delete_item, item.model_dump(mode="json", by_alias=True))

    @webonly
    async def delete_item_by_key(self, item_key: str) -> None:
        """Delete item by key string."""
        raw_item = await _run_sync(self._client.item, item_key)
        await _run_sync(self._client.delete_item, raw_item)

    @webonly
    async def delete_collection_by_key(self, collection_key: str) -> None:
        """Delete collection by key."""
        raw_coll = await _run_sync(self._client.collection, collection_key)
        await _run_sync(self._client.delete_collection, raw_coll)

    @webonly
    async def create_items(self, items: list[ItemCreate]) -> list[ZoteroItem]:
        """Create new items in Zotero library.

        Raises:
            ZoteroWriteError: If any items failed to create
        """
        try:
            items_data = [item.model_dump(exclude_none=True, by_alias=True) for item in items]
            try:
                raw_response = await _run_sync(self._client.create_items, items_data)
            except zotero_errors.UserNotAuthorisedError as e:
                raise ZoteroError(
                    "Not authorized to create items. "
                    "Hint: check that ZOTERO_API_KEY has write permissions."
                ) from e
            except zotero_errors.PyZoteroError as e:
                raise ZoteroError(
                    f"Zotero API error during item creation: {e}. "
                    "Hint: verify web API credentials and connectivity."
                ) from e

            response = ZoteroWriteResponse.model_validate(raw_response)

            if response.has_failures():
                raise ZoteroWriteError("create_items", response.failed)

            successful_items = response.get_successful_objects()
            return [ZoteroItem.model_validate(item_dict) for item_dict in successful_items]
        except ZoteroError:
            raise
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error creating items: {type(e).__name__}: {e}. "
                "Hint: check network connectivity and web API credentials."
            ) from e

    async def get_children(self, item_key: str) -> list[Attachment]:
        """Get child attachments for an item."""
        try:
            children_data = await _run_sync(self._client.children, item_key)
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
        except zotero_errors.ResourceNotFoundError as e:
            raise ZoteroNotFoundError("item", item_key) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Failed to get children for item '{item_key}': {e}. "
                "Hint: verify the item key is correct."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error getting children for item '{item_key}': "
                f"{type(e).__name__}: {e}. "
                "Hint: check network connectivity and Zotero availability."
            ) from e

    @webonly
    async def update_item(self, item_key: str, update: ItemUpdate) -> None:
        """Update an existing item."""
        try:
            try:
                item_dict = await _run_sync(self._client.item, item_key)
            except zotero_errors.ResourceNotFoundError as e:
                raise ZoteroNotFoundError("item", item_key) from e
            except zotero_errors.PyZoteroError as e:
                raise ZoteroError(
                    f"Failed to fetch item '{item_key}' for update: {e}. "
                    "Hint: verify the item key is correct."
                ) from e

            update_data = update.model_dump(exclude_none=True, by_alias=True)
            for key, value in update_data.items():
                item_dict["data"][key] = value

            try:
                await _run_sync(self._client.update_item, item_dict)
            except zotero_errors.PreConditionFailedError as e:
                raise ZoteroError(
                    f"Update conflict for item '{item_key}': version mismatch. "
                    "Hint: the item was modified by another client. Retry after re-fetching."
                ) from e
            except zotero_errors.UserNotAuthorisedError as e:
                raise ZoteroError(
                    f"Not authorized to update item '{item_key}'. "
                    "Hint: check that ZOTERO_API_KEY has write permissions."
                ) from e
            except zotero_errors.PyZoteroError as e:
                raise ZoteroError(
                    f"Zotero API error updating item '{item_key}': {e}. "
                    "Hint: verify web API credentials and connectivity."
                ) from e
        except ZoteroError:
            raise
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error updating item '{item_key}': {type(e).__name__}: {e}. "
                "Hint: check network connectivity and web API credentials."
            ) from e

    async def search_items(self, search_params: ZoteroSearchParams) -> list[ZoteroItem]:
        """Search top-level items across entire library with Zotero API parameters.

        Uses pyzotero's top() method with search parameters, fetching all results
        with automatic pagination via everything().
        """
        api_params = search_params.to_api_params()
        try:
            raw_items = await _run_sync(
                lambda: self._client.everything(self._client.top(**api_params))
            )
        except zotero_errors.UnsupportedParamsError as e:
            raise ZoteroError(
                f"Invalid search parameters: {e}. " "Hint: check query, item_type, and tag values."
            ) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Zotero API error during search: {e}. "
                "Hint: verify Zotero is running and accessible."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error during search: {type(e).__name__}: {e}. "
                "Hint: check network connectivity and Zotero availability."
            ) from e
        return [ZoteroItem.model_validate(item) for item in raw_items]

    async def search_collection_items(
        self, collection_key: str, search_params: ZoteroSearchParams
    ) -> list[ZoteroItem]:
        """Search top-level items within a specific collection using Zotero API parameters.

        Uses pyzotero's collection_items_top() with search parameters,
        fetching all results with automatic pagination via everything().
        """
        api_params = search_params.to_api_params()
        try:
            raw_items = await _run_sync(
                lambda: self._client.everything(
                    self._client.collection_items_top(collection_key, **api_params)
                )
            )
        except zotero_errors.ResourceNotFoundError as e:
            raise ZoteroNotFoundError("collection", collection_key) from e
        except zotero_errors.UnsupportedParamsError as e:
            raise ZoteroError(
                f"Invalid search parameters for collection '{collection_key}': {e}. "
                "Hint: check query, item_type, and tag values."
            ) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Zotero API error searching collection '{collection_key}': {e}. "
                "Hint: verify the collection key is correct and Zotero is accessible."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error searching collection '{collection_key}': "
                f"{type(e).__name__}: {e}. "
                "Hint: check network connectivity and Zotero availability."
            ) from e
        return [ZoteroItem.model_validate(item) for item in raw_items]

    @webonly
    async def create_collections(
        self, collections: list[CollectionCreate]
    ) -> list[ZoteroCollectionBase]:
        """Create new collections.

        Raises:
            ZoteroWriteError: If any collections failed to create
        """
        try:
            collections_data = [
                {"name": c.name, "parentCollection": c.parent_collection} for c in collections
            ]
            try:
                raw_response = await _run_sync(self._client.create_collections, collections_data)
            except zotero_errors.UserNotAuthorisedError as e:
                raise ZoteroError(
                    "Not authorized to create collections. "
                    "Hint: check that ZOTERO_API_KEY has write permissions."
                ) from e
            except zotero_errors.PyZoteroError as e:
                raise ZoteroError(
                    f"Zotero API error during collection creation: {e}. "
                    "Hint: verify web API credentials and connectivity."
                ) from e

            response = ZoteroWriteResponse.model_validate(raw_response)

            if response.has_failures():
                raise ZoteroWriteError("create_collections", response.failed)

            successful_colls = response.get_successful_objects()
            validated_colls = [
                ZoteroCollectionResponse.model_validate(coll) for coll in successful_colls
            ]
            return [
                Collection(self._client, coll.model_dump(mode="json")) for coll in validated_colls
            ]
        except ZoteroError:
            raise
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error creating collections: {type(e).__name__}: {e}. "
                "Hint: check network connectivity and web API credentials."
            ) from e

    @webonly
    async def add_to_collection(self, collection_key: str, items: list[ZoteroItem]) -> None:
        """Add items to a collection."""
        for item in items:
            try:
                await _run_sync(
                    self._client.addto_collection,
                    collection_key,
                    item.model_dump(by_alias=True),
                )
            except zotero_errors.ResourceNotFoundError as e:
                raise ZoteroNotFoundError("collection", collection_key) from e
            except zotero_errors.UserNotAuthorisedError as e:
                raise ZoteroError(
                    f"Not authorized to modify collection '{collection_key}'. "
                    "Hint: check that ZOTERO_API_KEY has write permissions."
                ) from e
            except zotero_errors.PyZoteroError as e:
                raise ZoteroError(
                    f"Failed to add item '{item.key}' to collection '{collection_key}': {e}. "
                    "Hint: verify the collection key exists and credentials are correct."
                ) from e
            except Exception as e:
                raise ZoteroError(
                    f"Unexpected error adding item '{item.key}' to collection "
                    f"'{collection_key}': {type(e).__name__}: {e}. "
                    "Hint: check network connectivity and web API credentials."
                ) from e

    @webonly
    async def remove_from_collection(self, collection_key: str, item_key: str) -> None:
        """Remove item from collection without deleting from library."""
        try:
            raw_item = await _run_sync(self._client.item, item_key)
        except zotero_errors.ResourceNotFoundError as e:
            raise ZoteroNotFoundError("item", item_key) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Failed to fetch item '{item_key}' for removal from collection: {e}. "
                "Hint: verify the item key is correct."
            ) from e
        try:
            await _run_sync(self._client.deletefrom_collection, collection_key, raw_item)
        except zotero_errors.ResourceNotFoundError as e:
            raise ZoteroNotFoundError("collection", collection_key) from e
        except zotero_errors.UserNotAuthorisedError as e:
            raise ZoteroError(
                f"Not authorized to modify collection '{collection_key}'. "
                "Hint: check that ZOTERO_API_KEY has write permissions."
            ) from e
        except zotero_errors.PyZoteroError as e:
            raise ZoteroError(
                f"Failed to remove item '{item_key}' from collection '{collection_key}': {e}. "
                "Hint: verify the collection key exists and credentials are correct."
            ) from e
        except Exception as e:
            raise ZoteroError(
                f"Unexpected error removing item '{item_key}' from collection "
                f"'{collection_key}': {type(e).__name__}: {e}. "
                "Hint: check network connectivity and web API credentials."
            ) from e
