from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigurationError


class Settings(BaseSettings):
    """Configuration with Pydantic validation and automatic .env loading."""

    # Zotero settings
    zotero_local: bool = Field(default=True)
    zotero_library_id: str = Field(default="")
    zotero_api_key: str | None = Field(default=None)
    zotero_library_type: str = Field(default="user")
    zotero_port: int = Field(default=23119)

    # Performance settings
    # Max tokens per chunk (estimated as len/4). Claude Code tool result limit is ~10K tokens,
    # so 5000 content tokens + JSON metadata overhead fits safely within that limit.
    max_chunk_size: int = Field(default=5000)
    # Max parallel requests to Zotero Web API (prevents 429 rate limiting).
    # Only applies in web mode; local mode has no rate limits.
    web_zotero_max_concurrent_requests: int = Field(default=5)

    # External fulltext retrieval
    unpaywall_email: str | None = Field(default=None)
    core_api_key: str | None = Field(default=None)
    fulltext_libgen_enabled: bool = Field(default=False)
    fulltext_libgen_mirror: str = Field(default="https://libgen.is")

    @model_validator(mode="after")
    def validate_credentials(self) -> Self:
        """Validate credentials based on mode."""
        if not self.zotero_local:
            # Web mode requires both library_id and api_key
            if not self.zotero_library_id:
                raise ConfigurationError("ZOTERO_LIBRARY_ID required for web mode")
            if not self.zotero_api_key:
                raise ConfigurationError("ZOTERO_API_KEY required for web mode")
        else:
            # Local mode: set default library_id if not provided
            # (pyzotero requires it even for local mode, but value doesn't matter)
            if not self.zotero_library_id:
                self.zotero_library_id = "1"
        return self

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.test"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
