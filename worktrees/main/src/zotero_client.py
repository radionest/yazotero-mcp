from typing import Any

from pyzotero import zotero

from .config import settings
from .models import Author, ZoteroItem


class LocalZoteroClient:
    """Placeholder for local Zotero client implementation."""

    def __init__(self) -> None:
        pass

    def collection_items(self, collection_key: str) -> list[dict[str, Any]]:
        return []

    def collections_sub(self, collection_key: str) -> list[dict[str, Any]]:
        return []

    def item(self, item_key: str) -> dict[str, Any]:
        return {"key": item_key, "data": {}}

    def items(self) -> list[dict[str, Any]]:
        """Get all items from local library."""
        return []

    def children(self, item_key: str) -> list[dict[str, Any]]:
        return []

    def create_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create new items in local library."""
        # Return mock created items with keys
        return [{"key": f"mock_{i}", "data": item} for i, item in enumerate(items)]

    def update_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Update existing item in local library."""
        return item


class ZoteroClient:
    """Simplified client supporting both local and web access."""

    def __init__(self) -> None:
        if settings.zotero_local:
            self.mode = "local"
            self.client = self._init_local_client()
        else:
            self.mode = "web"
            self.client = self._init_web_client()

        self.cache: dict[str, Any] = {}  # Simple in-memory cache

    def _init_web_client(self) -> Any:
        library_id = settings.zotero_library_id
        api_key = settings.zotero_api_key
        library_type = settings.zotero_library_type

        if not library_id or not api_key:
            raise ValueError("ZOTERO_LIBRARY_ID and ZOTERO_API_KEY required")

        return zotero.Zotero(library_id, library_type, api_key)

    def _init_local_client(self) -> LocalZoteroClient:
        # Use local Zotero SQLite database
        # Simplified implementation
        return LocalZoteroClient()

    async def get_collection_items(
        self, collection_key: str, include_children: bool = True
    ) -> list[ZoteroItem]:
        """Get all items in a collection."""
        cache_key = f"collection:{collection_key}"

        if cache_key in self.cache:
            return self.cache[cache_key]  # type: ignore[no-any-return]

        items: list[dict[str, Any]] = self.client.collection_items(collection_key)

        # Include child collections if requested
        if include_children:
            child_collections = self.client.collections_sub(collection_key)
            for child in child_collections:
                child_items = await self.get_collection_items(child["key"], False)
                # Convert ZoteroItems back to dicts for consistency
                for item in child_items:
                    items.append(self._item_to_dict(item))

        # Extract essential fields
        result = []
        for item_dict in items:
            if item_dict["data"]["itemType"] != "attachment":
                result.append(
                    ZoteroItem(
                        key=item_dict["key"],
                        title=item_dict["data"].get("title", ""),
                        abstractNote=item_dict["data"].get("abstractNote", ""),
                        authors=self._extract_authors(item_dict["data"]),
                        year=item_dict["data"].get("date", ""),
                        tags=[tag["tag"] for tag in item_dict["data"].get("tags", [])],
                    )
                )

        self.cache[cache_key] = result
        return result

    async def get_fulltext(self, item_key: str) -> str | None:
        """Get full text content if available."""
        cache_key = f"fulltext:{item_key}"

        if cache_key in self.cache:
            return self.cache[cache_key]  # type: ignore[no-any-return]

        # Try to get PDF attachment
        attachments = self.client.children(item_key)

        for attachment in attachments:
            if attachment["data"].get("contentType") == "application/pdf":
                # In real implementation, extract text from PDF
                # For now, return placeholder
                content = f"[Full text extraction needed for {item_key}]"
                self.cache[cache_key] = content
                return content

        return None

    def _extract_authors(self, data: dict[str, Any]) -> list[Author]:
        """Extract author names from item data."""
        authors = []
        for creator in data.get("creators", []):
            if creator.get("creatorType") == "author":
                authors.append(
                    Author(
                        first_name=creator.get("firstName", ""),
                        last_name=creator.get("lastName", ""),
                    )
                )
        return authors

    def _item_to_dict(self, item: ZoteroItem) -> dict[str, Any]:
        """Convert ZoteroItem back to dict for compatibility."""
        return {
            "key": item.key,
            "data": {
                "title": item.title,
                "abstractNote": item.abstract,
                "itemType": "journalArticle",
                "creators": [
                    {
                        "creatorType": "author",
                        "firstName": author.first_name,
                        "lastName": author.last_name,
                    }
                    for author in item.authors
                ],
                "date": item.year,
                "tags": [{"tag": tag} for tag in item.tags],
            },
        }

    async def get_item(self, item_key: str) -> ZoteroItem:
        """Get single item by key."""
        item = self.client.item(item_key)
        return ZoteroItem(
            key=item["key"],
            title=item["data"].get("title", ""),
            abstractNote=item["data"].get("abstractNote", ""),
            authors=self._extract_authors(item["data"]),
            year=item["data"].get("date", ""),
            tags=[tag["tag"] for tag in item["data"].get("tags", [])],
        )
