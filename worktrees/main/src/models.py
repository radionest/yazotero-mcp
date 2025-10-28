from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    pass


class ZoteroTag(BaseModel):
    """Zotero tag model.

    Represents a tag in Zotero with its name and type.
    Type field: 0 = automatic/colored tag, 1 = manual/user-created tag.
    """

    tag: str
    type: int = 0


class AnalysisType(str, Enum):
    SUMMARY = "summary"
    KEY_POINTS = "key_points"
    METHODS = "methods"
    BASIC = "basic"


class NoteAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    SEARCH = "search"


class ZoteroItemData(BaseModel):
    """Item data fields from Zotero API (nested under 'data' key)."""

    title: str = ""
    abstract_note: str = Field("", alias="abstractNote")
    item_type: str = Field("", alias="itemType")
    creators: list[dict[str, str]] = Field(default_factory=list)
    date: str = ""
    tags: list[ZoteroTag] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    # Allow additional fields for different item types
    model_config = {"extra": "allow", "populate_by_name": True}


class ZoteroItem(BaseModel):
    """Complete item structure from Zotero API.

    Represents the full raw item response with key, version, and nested data.
    Use properties for convenient access to nested fields.
    """

    model_config = {"extra": "ignore"}

    key: str
    version: int
    data: ZoteroItemData
    # Non-API field for full text content (loaded separately, not part of API response)
    fulltext: str | None = None

    @property
    def title(self) -> str:
        """Convenient access to title."""
        return self.data.title

    @property
    def abstract(self) -> str:
        """Convenient access to abstract."""
        return self.data.abstract_note

    @property
    def item_type(self) -> str:
        """Convenient access to item type."""
        return self.data.item_type

    @property
    def year(self) -> str:
        """Convenient access to date/year."""
        return self.data.date

    @computed_field
    def tags(self) -> list[str]:
        """Convenient access to tags as simple strings."""
        return [tag.tag for tag in self.data.tags]

    @property
    def creators(self) -> list[dict[str, str]]:
        """Raw creators list."""
        return self.data.creators

    def get_authors(self) -> list[tuple[str, str]]:
        """Extract authors as (first_name, last_name) tuples."""
        authors = []
        for creator in self.data.creators:
            if creator.get("creatorType") == "author":
                authors.append((creator.get("firstName", ""), creator.get("lastName", "")))
        return authors


class Note(BaseModel):
    key: str
    parent_key: str | None = None
    content: str
    created: datetime
    modified: datetime
    tags: list[str] = []


class TextSummary(BaseModel):
    abstract: str
    introduction: str
    methods: str
    results: str
    conclusion: str
    word_count: int
    sections_found: list[str]


class SearchCollectionResponse(BaseModel):
    items: list[ZoteroItem]
    count: int
    has_more: bool = False
    chunk_id: str | None = None
    current_chunk: int | None = None
    total_chunks: int | None = None
    message: str | None = None
    error: str | None = None

    @property
    def chunk_info(self) -> str | None:
        """Backward compatibility property for chunk info string."""
        if self.current_chunk is not None and self.total_chunks is not None:
            return f"{self.current_chunk}/{self.total_chunks}"
        return None


class ManageNotesResponse(BaseModel):
    note: Note | None = None
    notes: list[Note] | None = None
    count: int | None = None
    error: str | None = None


class FulltextResponse(BaseModel):
    """Response for fulltext content with chunking support."""

    item_key: str
    content: str  # Current chunk of text
    has_more: bool = False
    chunk_id: str | None = None
    current_chunk: int | None = None
    total_chunks: int | None = None
    message: str | None = None
    error: str | None = None

    @property
    def chunk_info(self) -> str | None:
        """Chunk progress information."""
        if self.current_chunk is not None and self.total_chunks is not None:
            return f"{self.current_chunk}/{self.total_chunks}"
        return None


class ChunkResponse(BaseModel):
    items: list[ZoteroItem]
    has_more: bool
    chunk_id: str | None = None
    current_chunk: int | None = None
    total_chunks: int | None = None
    error: str | None = None

    @property
    def chunk_info(self) -> str | None:
        """Backward compatibility property for chunk info string."""
        if self.current_chunk is not None and self.total_chunks is not None:
            return f"{self.current_chunk}/{self.total_chunks}"
        return None


# Zotero API data models for type-safe client operations


class ItemCreate(BaseModel):
    """Model for creating new Zotero items (notes, attachments, etc)."""

    item_type: str = Field(alias="itemType")
    parent_item: str | None = Field(None, alias="parentItem")
    note: str | None = None
    tags: list[ZoteroTag] = Field(default_factory=list)
    # Allow additional fields for different item types
    model_config = {"extra": "allow", "populate_by_name": True}


class ItemUpdate(BaseModel):
    """Model for updating existing Zotero items."""

    note: str | None = None
    tags: list[ZoteroTag] | None = None
    # Allow additional fields for different item types
    model_config = {"extra": "allow"}


class Attachment(BaseModel):
    """Model for Zotero item attachments (PDFs, files, etc)."""

    key: str
    item_type: str = Field(alias="itemType")
    content_type: str | None = Field(None, alias="contentType")
    filename: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class CollectionCreate(BaseModel):
    """Model for creating new Zotero collections."""

    name: str
    parent_collection: str | None = Field(None, alias="parentCollection")

    model_config = {"populate_by_name": True}


# Zotero API Write Response Models


class ZoteroFailedItem(BaseModel):
    """Failed item details from Zotero write operations."""

    key: str
    code: int
    message: str


class ZoteroWriteResponse(BaseModel):
    """Response from Zotero write operations (create/update).

    Follows format: {"successful": {...}, "unchanged": {...}, "failed": {...}}
    where keys are string indexes corresponding to request array positions.
    """

    successful: dict[str, dict[str, Any]] = Field(default_factory=dict)
    unchanged: dict[str, str] = Field(default_factory=dict)
    failed: dict[str, ZoteroFailedItem] = Field(default_factory=dict)

    def has_failures(self) -> bool:
        """Check if response contains any failed items."""
        return len(self.failed) > 0

    def get_successful_keys(self) -> list[str]:
        """Extract item/collection keys from successful operations."""
        return [data.get("key", "") for data in self.successful.values() if "key" in data]

    def get_successful_objects(self) -> list[dict[str, Any]]:
        """Get all successfully created/updated objects."""
        return list(self.successful.values())


class ZoteroCollectionData(BaseModel):
    """Collection data fields from Zotero API (nested under 'data' key)."""

    name: str
    parent_collection: str | bool | None = Field(default=None, alias="parentCollection")

    model_config = {"extra": "allow", "populate_by_name": True}


class ZoteroCollectionResponse(BaseModel):
    """Complete collection structure from Zotero API.

    Represents full collection response with key, version, and nested data.
    """

    key: str
    version: int
    data: ZoteroCollectionData

    model_config = {"extra": "ignore"}
