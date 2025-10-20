import json
import uuid
from typing import Any

from .config import settings
from .models import ChunkResponse, ZoteroItem


class ResponseChunker:
    """Simple response chunking for large results."""

    def __init__(self, max_tokens: int | None = None):
        self.max_tokens = max_tokens or settings.max_chunk_size
        self.chunks_store: dict[str, dict[str, Any]] = {}  # In-memory storage

    def estimate_tokens(self, data: Any) -> int:
        """Simple token estimation (4 chars = 1 token)."""
        if isinstance(data, str):
            return len(data) // 4
        else:
            return len(json.dumps(data, default=str)) // 4

    def needs_chunking(self, data: list[ZoteroItem]) -> bool:
        """Check if data needs chunking."""
        total_tokens = self.estimate_tokens([item.dict() for item in data])
        return total_tokens > self.max_tokens

    def chunk_response(self, data: list[ZoteroItem]) -> ChunkResponse:
        """Chunk list of items if too large."""
        total_tokens = self.estimate_tokens([item.dict() for item in data])

        if total_tokens <= self.max_tokens:
            return ChunkResponse(items=data, has_more=False)

        # Calculate items per chunk
        items_per_chunk = max(1, len(data) * self.max_tokens // total_tokens)

        # Create chunks
        chunks = [data[i : i + items_per_chunk] for i in range(0, len(data), items_per_chunk)]

        if len(chunks) == 1:
            return ChunkResponse(items=chunks[0], has_more=False)

        # Store remaining chunks
        chunk_id = str(uuid.uuid4())
        self.chunks_store[chunk_id] = {"chunks": chunks[1:], "current": 1, "total": len(chunks)}

        return ChunkResponse(
            items=chunks[0], has_more=True, chunk_id=chunk_id, chunk_info=f"1/{len(chunks)}"
        )

    def get_next_chunk(self, chunk_id: str) -> ChunkResponse:
        """Get next chunk by ID."""
        if chunk_id not in self.chunks_store:
            return ChunkResponse(items=[], has_more=False, error="Invalid or expired chunk ID")

        store = self.chunks_store[chunk_id]

        if not store["chunks"]:
            del self.chunks_store[chunk_id]
            return ChunkResponse(items=[], has_more=False)

        next_chunk = store["chunks"].pop(0)
        store["current"] += 1

        has_more = len(store["chunks"]) > 0

        if not has_more:
            del self.chunks_store[chunk_id]

        return ChunkResponse(
            items=next_chunk,
            has_more=has_more,
            chunk_id=chunk_id if has_more else None,
            chunk_info=f"{store['current']}/{store['total']}",
        )
