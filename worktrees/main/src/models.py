from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    pass


# Abstract base classes for Zotero collections and iterators


class ZoteroItemIterator(ABC):
    """Abstract base class for Zotero item iterators.

    Provides lazy iteration over Zotero items with pagination support.
    """

    @abstractmethod
    def __len__(self) -> int:
        """Get total count of items without loading all of them."""
        ...

    @abstractmethod
    def __iter__(self) -> Iterator["ZoteroItem"]:
        """Iterate over all items, fetching in batches as needed."""
        ...

    @abstractmethod
    def all(self) -> list["ZoteroItem"]:
        """Fetch all items at once."""
        ...

    @abstractmethod
    def keys(self) -> list[str]:
        """Get all item keys."""
        ...


class ZoteroCollectionBase(ABC):
    """Abstract base class for Zotero collections.

    Represents a collection with lazy-loaded items and subcollections.
    """

    @property
    @abstractmethod
    def key(self) -> str:
        """Collection key."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Collection name."""
        ...

    @property
    @abstractmethod
    def version(self) -> int:
        """Collection version."""
        ...

    @property
    @abstractmethod
    def items(self) -> ZoteroItemIterator:
        """Lazy iterator over items in this collection."""
        ...

    @property
    @abstractmethod
    def subcollections(self) -> list["ZoteroCollectionBase"]:
        """Get subcollections (loaded once)."""
        ...

    @abstractmethod
    def delete(self) -> None:
        """Delete this collection."""
        ...

    @abstractmethod
    def __repr__(self) -> str:
        """String representation of the collection."""
        ...


class ZoteroTag(BaseModel):
    """Zotero tag model.

    Represents a tag in Zotero with its name and type.
    Type field: 0 = automatic/colored tag, 1 = manual/user-created tag.
    """

    tag: str
    type: int = 0


class ZoteroCreator(BaseModel):
    """Zotero creator (author, editor, etc.) model.

    Supports two formats:
    - firstName/lastName for individuals
    - name for organizations
    """

    creator_type: str = Field(alias="creatorType")
    first_name: str | None = Field(None, alias="firstName")
    last_name: str | None = Field(None, alias="lastName")
    name: str | None = None

    model_config = {"populate_by_name": True}


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

    # Core fields (common to all item types)
    item_type: str = Field("", alias="itemType")
    title: str = ""
    creators: list[ZoteroCreator] = Field(default_factory=list)
    abstract_note: str = Field("", alias="abstractNote")
    date: str = ""
    tags: list[ZoteroTag] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)

    # Identifiers
    doi: str | None = Field(None, alias="DOI")
    url: str | None = None
    isbn: str | None = Field(None, alias="ISBN")
    issn: str | None = Field(None, alias="ISSN")

    # Publication fields (journalArticle, conferencePaper)
    publication_title: str | None = Field(None, alias="publicationTitle")
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None

    # Conference fields
    proceedings_title: str | None = Field(None, alias="proceedingsTitle")

    # Book fields
    publisher: str | None = None

    # Note fields
    note: str | None = None
    parent_item: str | None = Field(None, alias="parentItem")

    model_config = {"populate_by_name": True}


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
    def creators(self) -> list[ZoteroCreator]:
        """Raw creators list."""
        return self.data.creators

    def get_authors(self) -> list[tuple[str, str]]:
        """Extract authors as (first_name, last_name) tuples."""
        authors = []
        for creator in self.data.creators:
            if creator.creator_type == "author":
                authors.append((creator.first_name or "", creator.last_name or ""))
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
    """Model for creating new Zotero items (articles, books, notes, etc).

    Supports all common Zotero item types with type-safe field validation.
    """

    # Core fields (itemType is required for creation)
    item_type: str = Field(alias="itemType")
    title: str = ""
    creators: list[ZoteroCreator] = Field(default_factory=list)
    abstract_note: str | None = Field(None, alias="abstractNote")
    date: str = ""
    tags: list[ZoteroTag] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)

    # Identifiers
    doi: str | None = Field(None, alias="DOI")
    url: str | None = None
    isbn: str | None = Field(None, alias="ISBN")
    issn: str | None = Field(None, alias="ISSN")

    # Publication fields (journalArticle, conferencePaper)
    publication_title: str | None = Field(None, alias="publicationTitle")
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None

    # Conference fields
    proceedings_title: str | None = Field(None, alias="proceedingsTitle")

    # Book fields
    publisher: str | None = None

    # Note fields
    note: str | None = None
    parent_item: str | None = Field(None, alias="parentItem")

    model_config = {"populate_by_name": True}


class ItemUpdate(BaseModel):
    """Model for updating existing Zotero items.

    All fields are optional - only specified fields will be updated.
    Use exclude_none=True when serializing for PATCH-like behavior.
    """

    # Core fields (all optional for updates)
    item_type: str | None = Field(None, alias="itemType")
    title: str | None = None
    creators: list[ZoteroCreator] | None = None
    abstract_note: str | None = Field(None, alias="abstractNote")
    date: str | None = None
    tags: list[ZoteroTag] | None = None
    collections: list[str] | None = None

    # Identifiers
    doi: str | None = Field(None, alias="DOI")
    url: str | None = None
    isbn: str | None = Field(None, alias="ISBN")
    issn: str | None = Field(None, alias="ISSN")

    # Publication fields
    publication_title: str | None = Field(None, alias="publicationTitle")
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None

    # Conference fields
    proceedings_title: str | None = Field(None, alias="proceedingsTitle")

    # Book fields
    publisher: str | None = None

    # Note fields
    note: str | None = None
    parent_item: str | None = Field(None, alias="parentItem")

    model_config = {"populate_by_name": True}


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
