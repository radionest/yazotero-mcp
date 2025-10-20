from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class Settings(BaseModel):
    """Configuration with Pydantic validation."""

    # Zotero settings
    zotero_local: bool = Field(default=False)
    zotero_library_id: str = Field(default="")
    zotero_api_key: str | None = Field(default=None)
    zotero_library_type: str = Field(default="user")

    # Performance settings
    max_chunk_size: int = Field(default=20000)
    cache_ttl: int = Field(default=300)

    @field_validator("zotero_library_id")
    @classmethod
    def validate_library_id(cls, v: str, info: ValidationInfo) -> str:
        values = info.data if hasattr(info, "data") else {}
        if not values.get("zotero_local") and not v:
            raise ValueError("ZOTERO_LIBRARY_ID required for web mode")
        return v

    @field_validator("zotero_api_key")
    @classmethod
    def validate_api_key(cls, v: str | None, info: ValidationInfo) -> str | None:
        values = info.data if hasattr(info, "data") else {}
        if not values.get("zotero_local") and not v:
            raise ValueError("ZOTERO_API_KEY required for web mode")
        return v

    model_config = ConfigDict()


# Singleton
settings = Settings()
