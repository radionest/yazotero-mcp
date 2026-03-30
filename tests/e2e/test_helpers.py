"""Utilities for managing test data in real Zotero library."""

import random
import string
from typing import Any

from yazot.models import ZoteroItem
from yazot.zotero_client import ZoteroClient


class ZoteroTestDataManager:
    """Manages creation and cleanup of test data in Zotero library."""

    def __init__(self, client: ZoteroClient) -> None:
        """Initialize test data manager.

        Args:
            client: ZoteroClient instance for API operations
        """
        self.client = client
        self.created_items: list[ZoteroItem] = []
        self.created_collections: list[str] = []

        # Track if we're in web mode (cleanup only works for web API)
        self.can_cleanup = self.client.mode == "web"

    async def generate_item_data(
        self,
        template_type: str = "journalArticle",
        title_prefix: str = "Test Article",
        **overrides: Any,
    ) -> dict[str, Any]:
        """Generate valid item data based on template.

        Args:
            template_type: Zotero item type (journalArticle, book, etc.)
            title_prefix: Prefix for generated title
            **overrides: Additional fields to override in template

        Returns:
            Valid item data dictionary
        """
        # Get template from Zotero API
        template = await self.client.get_item_template(template_type)

        # Generate unique title
        random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        template["title"] = f"{title_prefix} {random_suffix}"

        # Add sample data
        template["abstractNote"] = f"Test abstract for {template['title']}"
        template["date"] = "2024"
        template["creators"] = [
            {
                "creatorType": "author",
                "firstName": "Test",
                "lastName": f"Author{random_suffix}",
            }
        ]
        template["tags"] = [{"tag": "test", "type": 1}, {"tag": f"auto-{random_suffix}", "type": 0}]

        # Apply overrides
        template.update(overrides)

        return template

    async def generate_attachment_data(
        self,
        parent_key: str,
        link_mode: str = "linked_url",
        title: str = "Test PDF",
        url: str = "https://example.com/test.pdf",
    ) -> dict[str, Any]:
        """Generate attachment data for creating PDF attachments.

        Args:
            parent_key: Key of parent item
            link_mode: Attachment link mode ('linked_url', 'imported_file', etc.)
            title: Attachment title
            url: URL for linked attachments

        Returns:
            Valid attachment data dictionary
        """
        # Get attachment template
        template = await self.client.get_item_template("attachment")

        # Configure as linked URL attachment (simplest for testing)
        template["linkMode"] = link_mode
        template["title"] = title
        template["url"] = url
        template["contentType"] = "application/pdf"
        template["parentItem"] = parent_key

        return template

    def generate_collection_data(self, name: str, parent_key: str | None = None) -> dict[str, Any]:
        """Generate collection data.

        Args:
            name: Collection name
            parent_key: Optional parent collection key for nesting

        Returns:
            Collection data dictionary
        """
        collection_data = {"name": name}
        if parent_key:
            collection_data["parentCollection"] = parent_key

        return collection_data

    async def batch_create_items(
        self,
        items_data: list[dict[str, Any]],
        batch_size: int = 50,
    ) -> list[ZoteroItem]:
        """Create items in batches respecting API limits.

        Args:
            items_data: List of item data dictionaries
            batch_size: Max items per API call (default 50)

        Returns:
            List of created item keys
        """
        from yazot.models import ItemCreate

        created_items = []

        # Create in batches
        for i in range(0, len(items_data), batch_size):
            batch_data = items_data[i : i + batch_size]
            # Convert to ItemCreate models
            batch_items = [ItemCreate(**data) for data in batch_data]
            result = await self.client.create_items(batch_items)

            # Extract keys from ZoteroItem models
            for item in result:
                created_items.append(item)
                self.created_items.append(item)

        return created_items

    async def create_test_items(
        self,
        count: int,
        collection_key: str | None = None,
        template_type: str = "journalArticle",
    ) -> list[ZoteroItem]:
        """Create multiple test items.

        Args:
            count: Number of items to create
            collection_key: Optional collection to add items to
            template_type: Type of items to create

        Returns:
            List of created item keys
        """
        # Generate item data
        items_data = [
            await self.generate_item_data(template_type, f"Test Item {i}") for i in range(count)
        ]

        # Create items
        items = await self.batch_create_items(items_data)

        # Add to collection if specified
        if collection_key and items:
            await self.client.add_to_collection(collection_key, items)

        return items

    async def create_item_with_attachment(
        self,
        title: str = "Test Article with PDF",
        attachment_url: str = "https://example.com/test.pdf",
        collection_key: str | None = None,
    ) -> ZoteroItem:
        """Create a test item with a PDF attachment.

        Args:
            title: Title for the item
            attachment_url: URL for the PDF attachment
            collection_key: Optional collection to add item to

        Returns:
            Created item with attachment
        """
        # Create parent item
        item_data = await self.generate_item_data("journalArticle", title)
        items = await self.batch_create_items([item_data])
        parent_item = items[0]

        # Create attachment for the item
        attachment_data = await self.generate_attachment_data(
            parent_key=parent_item.key,
            title=f"PDF for {title}",
            url=attachment_url,
        )

        # Create the attachment
        from yazot.models import ItemCreate

        attachment_item = ItemCreate(**attachment_data)
        await self.client.create_items([attachment_item])

        # Add to collection if specified
        if collection_key:
            await self.client.add_to_collection(collection_key, [parent_item])

        return parent_item

    async def batch_create_collections(
        self,
        collections_data: list[dict[str, Any]],
        batch_size: int = 50,
    ) -> list[str]:
        """Create collections in batches.

        Args:
            collections_data: List of collection data dictionaries
            batch_size: Max collections per API call (default 50)

        Returns:
            List of created collection keys
        """
        from yazot.models import CollectionCreate

        created_keys = []

        for i in range(0, len(collections_data), batch_size):
            batch_data = collections_data[i : i + batch_size]
            # Convert to CollectionCreate models
            batch_collections = [CollectionCreate(**data) for data in batch_data]
            result = await self.client.create_collections(batch_collections)

            # Extract keys from Collection objects
            for collection in result:
                created_keys.append(collection.key)
                self.created_collections.append(collection.key)

        return created_keys

    async def create_test_collections(
        self,
        count: int,
        parent_key: str | None = None,
        name_prefix: str = "Test Collection",
    ) -> list[str]:
        """Create multiple test collections.

        Args:
            count: Number of collections to create
            parent_key: Optional parent collection key
            name_prefix: Prefix for collection names

        Returns:
            List of created collection keys
        """
        collections_data = [
            self.generate_collection_data(f"{name_prefix} {i}", parent_key) for i in range(count)
        ]

        return await self.batch_create_collections(collections_data)

    async def create_nested_collections(
        self,
        depth: int,
        width: int,
        root_name: str = "Test Root Collection",
    ) -> dict[str, list[str]]:
        """Create nested collection hierarchy.

        Args:
            depth: Number of nesting levels
            width: Number of collections at each level
            root_name: Name of root collection

        Returns:
            Dictionary mapping level to list of collection keys
        """
        hierarchy: dict[str, list[str]] = {}

        # Create root level
        root_keys = await self.create_test_collections(1, name_prefix=root_name)
        hierarchy["level_0"] = root_keys

        # Create nested levels
        for level in range(1, depth):
            parent_keys = hierarchy[f"level_{level - 1}"]
            level_keys = []

            for parent_key in parent_keys:
                child_keys = await self.create_test_collections(
                    width,
                    parent_key=parent_key,
                    name_prefix=f"L{level} Collection",
                )
                level_keys.extend(child_keys)

            hierarchy[f"level_{level}"] = level_keys

        return hierarchy

    async def refresh_items(self, items: list[ZoteroItem]) -> list[ZoteroItem]:
        """Re-fetch items from the server to get current versions.

        After add_to_collection the server bumps the item version.
        Subsequent operations need the fresh version to avoid 412 PreconditionFailed.
        """
        return [await self.client.get_item(item.key) for item in items]

    async def add_items_to_collection(self, items: list[ZoteroItem], collection_key: str) -> None:
        """Add existing items to collection.

        Args:
            items: List of items to add
            collection_key: Target collection key
        """
        await self.client.add_to_collection(collection_key, items)

    async def verify_item_count(self, collection_key: str, expected_count: int) -> bool:
        """Verify collection has expected number of items.

        Args:
            collection_key: Collection to check
            expected_count: Expected number of items

        Returns:
            True if count matches
        """
        collection = await self.client.get_collection(key=collection_key)
        items = await collection.get_items()
        return len(items) == expected_count

    async def cleanup(self) -> dict[str, int]:
        """Delete all created test data.

        Only works in web mode. Returns counts of deleted items.

        Returns:
            Dictionary with counts of deleted items and collections
        """
        deleted = {"items": 0, "collections": 0}

        if not self.can_cleanup:
            return deleted

        # Delete items (must be done before collections if items are in them)
        for item in self.created_items:
            try:
                await self.client.delete_item_by_key(item.key)
                deleted["items"] += 1
            except Exception:
                # Item may already be deleted or not exist
                pass

        # Delete collections (in reverse order to handle nested structures)
        for collection_key in reversed(self.created_collections):
            try:
                await self.client.delete_collection_by_key(collection_key)
                deleted["collections"] += 1
            except Exception:
                pass

        # Clear tracking lists
        self.created_items.clear()
        self.created_collections.clear()

        return deleted

    async def cleanup_entire_library(self) -> dict[str, int]:
        """Delete ALL items and collections in library (not just tracked ones).

        WARNING: This will delete everything in the library!
        Only works in web mode.

        Returns:
            Dictionary with counts of deleted items and collections
        """
        deleted = {"items": 0, "collections": 0}

        if not self.can_cleanup:
            return deleted

        # Delete all items
        all_items = await self.client.get_items()
        for item in all_items:
            try:
                await self.client.delete_item(item)
                deleted["items"] += 1
            except Exception:
                pass

        # Delete all collections (reverse order for nested structures)
        all_collections = await self.client.get_collections()
        for collection in reversed(all_collections):
            try:
                await self.client.delete_collection_by_key(collection.key)
                deleted["collections"] += 1
            except Exception:
                pass

        return deleted

    async def create_items_with_various_tags(
        self,
        collection_key: str | None = None,
    ) -> list[ZoteroItem]:
        """Create test items with various tag types for testing tag validation.

        Creates items with:
        - Manual tags (type=1)
        - Automatic tags (type=0)
        - Mix of both types

        Args:
            collection_key: Optional collection to add items to

        Returns:
            List of created items with various tag types
        """
        items_data = []

        # Item with only manual tags
        item1 = await self.generate_item_data(
            "journalArticle",
            "Item with Manual Tags",
            tags=[
                {"tag": "manual-tag-1", "type": 1},
                {"tag": "manual-tag-2", "type": 1},
            ],
        )
        items_data.append(item1)

        # Item with only automatic tags
        item2 = await self.generate_item_data(
            "journalArticle",
            "Item with Auto Tags",
            tags=[
                {"tag": "auto-tag-1", "type": 0},
                {"tag": "auto-tag-2", "type": 0},
            ],
        )
        items_data.append(item2)

        # Item with mixed tags
        item3 = await self.generate_item_data(
            "journalArticle",
            "Item with Mixed Tags",
            tags=[
                {"tag": "manual-mixed", "type": 1},
                {"tag": "auto-mixed", "type": 0},
                {"tag": "manual-mixed-2", "type": 1},
            ],
        )
        items_data.append(item3)

        # Item with no tags
        item4 = await self.generate_item_data(
            "journalArticle",
            "Item without Tags",
            tags=[],
        )
        items_data.append(item4)

        # Create items
        items = await self.batch_create_items(items_data)

        # Add to collection if specified
        if collection_key and items:
            await self.client.add_to_collection(collection_key, items)

        return items

    def get_stats(self) -> dict[str, int]:
        """Get statistics about created test data.

        Returns:
            Dictionary with counts of tracked items and collections
        """
        return {
            "items": len(self.created_items),
            "collections": len(self.created_collections),
            "can_cleanup": self.can_cleanup,
        }


async def create_bulk_test_data(
    client: ZoteroClient,
    num_collections: int = 10,
    items_per_collection: int = 100,
) -> tuple[ZoteroTestDataManager, list[str]]:
    """Helper to create bulk test data for stress testing.

    Args:
        client: ZoteroClient instance
        num_collections: Number of collections to create
        items_per_collection: Items to create in each collection

    Returns:
        Tuple of (manager, list of collection keys)
    """
    manager = ZoteroTestDataManager(client)

    # Create collections
    collection_keys = await manager.create_test_collections(num_collections)

    # Add items to each collection
    for coll_key in collection_keys:
        await manager.create_test_items(items_per_collection, coll_key)

    return manager, collection_keys
