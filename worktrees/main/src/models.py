from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


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


class SearchCollectionRequest(BaseModel):
    collection_key: str
    query: str | None = None
    include_fulltext: bool = False


class AnalyzeFulltextRequest(BaseModel):
    item_key: str
    analysis_type: AnalysisType = AnalysisType.SUMMARY


class ManageNotesRequest(BaseModel):
    action: NoteAction
    item_key: str | None = None
    content: str | None = None
    note_key: str | None = None
    search_query: str | None = None


class Author(BaseModel):
    first_name: str = ""
    last_name: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class ZoteroItem(BaseModel):
    key: str
    title: str
    abstract: str = Field(default="", alias="abstractNote")
    authors: list[Author] = []
    year: str = ""
    tags: list[str] = []
    fulltext: str | None = None


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


class MethodsAnalysis(BaseModel):
    study_type: str
    sample_size: str | None = None
    statistical_methods: list[str] = []
    summary: str


class SearchCollectionResponse(BaseModel):
    items: list[ZoteroItem]
    count: int
    has_more: bool = False
    chunk_id: str | None = None
    chunk_info: str | None = None
    error: str | None = None


class AnalyzeFulltextResponse(BaseModel):
    item_key: str
    title: str
    analysis_type: AnalysisType
    result: TextSummary | list[str] | MethodsAnalysis
    error: str | None = None


class ManageNotesResponse(BaseModel):
    note: Note | None = None
    notes: list[Note] | None = None
    count: int | None = None
    error: str | None = None


class ChunkResponse(BaseModel):
    items: list[ZoteroItem]
    has_more: bool
    chunk_id: str | None = None
    chunk_info: str | None = None
    error: str | None = None
