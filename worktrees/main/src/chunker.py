import json
import re
import uuid
from typing import Any

from .config import settings
from .exceptions import ZoteroNotFoundError
from .models import ChunkResponse, ZoteroItem


class ResponseChunker:
    """Simple response chunking for large results."""

    # Safety margin for response metadata (message, count, chunk_id, etc.)
    # MCP limit is 25000 tokens, we use 18000 for items to leave room for metadata
    METADATA_OVERHEAD = 2000
    MCP_TOKEN_LIMIT = 25000

    def __init__(self, max_tokens: int | None = None):
        self.max_tokens = max_tokens or settings.max_chunk_size
        # Apply safety margin to account for response metadata
        self.effective_max_tokens = self.max_tokens - self.METADATA_OVERHEAD
        self.chunks_store: dict[str, dict[str, Any]] = {}  # In-memory storage

    def estimate_tokens(self, data: Any) -> int:
        """Simple token estimation (4 chars = 1 token)."""
        if isinstance(data, str):
            return len(data) // 4
        else:
            return len(json.dumps(data, default=str)) // 4

    def estimate_response_tokens(
        self, items: list[ZoteroItem], include_metadata: bool = True
    ) -> int:
        """Estimate tokens for complete response including metadata.

        Args:
            items: List of items to estimate
            include_metadata: Whether to include overhead for response metadata

        Returns:
            Estimated token count for complete response
        """
        items_tokens = self.estimate_tokens([item.model_dump() for item in items])

        if include_metadata:
            # Add overhead for SearchCollectionResponse metadata:
            # count, has_more, chunk_id, current_chunk, total_chunks, message
            return items_tokens + self.METADATA_OVERHEAD

        return items_tokens

    def needs_chunking(self, data: list[ZoteroItem]) -> bool:
        """Check if data needs chunking.

        Uses effective_max_tokens (with safety margin) to ensure complete
        response stays under MCP_TOKEN_LIMIT.
        """
        total_tokens = self.estimate_tokens([item.model_dump() for item in data])
        return total_tokens > self.effective_max_tokens

    def chunk_response(self, data: list[ZoteroItem]) -> ChunkResponse:
        """Chunk list of items if too large."""
        total_tokens = self.estimate_tokens([item.model_dump() for item in data])

        if total_tokens <= self.effective_max_tokens:
            return ChunkResponse(items=data, has_more=False)

        # Calculate items per chunk using effective max tokens
        items_per_chunk = max(1, len(data) * self.effective_max_tokens // total_tokens)

        # Create chunks
        chunks = [data[i : i + items_per_chunk] for i in range(0, len(data), items_per_chunk)]

        if len(chunks) == 1:
            return ChunkResponse(items=chunks[0], has_more=False)

        # Store remaining chunks
        chunk_id = str(uuid.uuid4())
        self.chunks_store[chunk_id] = {"chunks": chunks[1:], "current": 1, "total": len(chunks)}

        return ChunkResponse(
            items=chunks[0],
            has_more=True,
            chunk_id=chunk_id,
            current_chunk=1,
            total_chunks=len(chunks),
        )

    def get_next_chunk(self, chunk_id: str) -> ChunkResponse:
        """Get next chunk by ID.

        Raises:
            ZoteroNotFoundError: If chunk_id is invalid or expired
        """
        if chunk_id not in self.chunks_store:
            raise ZoteroNotFoundError("chunk", chunk_id)

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
            current_chunk=store["current"],
            total_chunks=store["total"],
        )


class TextChunker:
    """Chunker for long text content (e.g., article fulltext)."""

    def __init__(self, max_tokens: int | None = None):
        self.max_tokens = max_tokens or settings.max_chunk_size
        self.text_store: dict[str, dict[str, Any]] = {}  # In-memory storage

    def estimate_tokens(self, text: str) -> int:
        """Simple token estimation (4 chars = 1 token)."""
        return len(text) // 4

    def needs_chunking(self, text: str) -> bool:
        """Check if text needs chunking."""
        return self.estimate_tokens(text) > self.max_tokens

    def _split_by_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs."""
        # Split by double newlines or multiple whitespace
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_by_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting (can be improved with nltk if needed)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def chunk_text(self, text: str, item_key: str) -> dict[str, Any]:
        """Chunk long text into manageable pieces.

        Returns dict with first chunk and metadata.
        """
        if not text or not text.strip():
            return {
                "item_key": item_key,
                "content": "",
                "has_more": False,
                "chunk_id": None,
                "current_chunk": None,
                "total_chunks": None,
            }

        total_tokens = self.estimate_tokens(text)

        if total_tokens <= self.max_tokens:
            return {
                "item_key": item_key,
                "content": text,
                "has_more": False,
                "chunk_id": None,
                "current_chunk": None,
                "total_chunks": None,
            }

        # Split text intelligently
        paragraphs = self._split_by_paragraphs(text)

        # Build chunks by paragraphs
        chunks: list[str] = []
        current_chunk = ""

        for para in paragraphs:
            para_tokens = self.estimate_tokens(para)
            current_tokens = self.estimate_tokens(current_chunk)

            # If single paragraph is too large, split by sentences
            if para_tokens > self.max_tokens:
                # Save current chunk if any
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                # Split large paragraph by sentences
                sentences = self._split_by_sentences(para)
                for sentence in sentences:
                    sentence_tokens = self.estimate_tokens(sentence)
                    current_sentence_tokens = self.estimate_tokens(current_chunk)

                    if current_sentence_tokens + sentence_tokens <= self.max_tokens:
                        current_chunk += (" " if current_chunk else "") + sentence
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sentence

            # Normal case: add paragraph to chunk
            elif current_tokens + para_tokens <= self.max_tokens:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                # Current chunk is full, start new one
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para

        # Add last chunk
        if current_chunk:
            chunks.append(current_chunk)

        if len(chunks) <= 1:
            return {
                "item_key": item_key,
                "content": chunks[0] if chunks else text,
                "has_more": False,
                "chunk_id": None,
                "current_chunk": None,
                "total_chunks": None,
            }

        # Store remaining chunks
        chunk_id = str(uuid.uuid4())
        self.text_store[chunk_id] = {
            "item_key": item_key,
            "chunks": chunks[1:],
            "current": 1,
            "total": len(chunks),
        }

        return {
            "item_key": item_key,
            "content": chunks[0],
            "has_more": True,
            "chunk_id": chunk_id,
            "current_chunk": 1,
            "total_chunks": len(chunks),
        }

    def get_next_text_chunk(self, chunk_id: str) -> dict[str, Any]:
        """Get next text chunk by ID.

        Raises:
            ZoteroNotFoundError: If chunk_id is invalid or expired
        """
        if chunk_id not in self.text_store:
            raise ZoteroNotFoundError("text chunk", chunk_id)

        store = self.text_store[chunk_id]

        if not store["chunks"]:
            del self.text_store[chunk_id]
            return {
                "item_key": store["item_key"],
                "content": "",
                "has_more": False,
                "chunk_id": None,
                "current_chunk": None,
                "total_chunks": None,
            }

        next_chunk = store["chunks"].pop(0)
        store["current"] += 1

        has_more = len(store["chunks"]) > 0

        if not has_more:
            item_key = store["item_key"]
            del self.text_store[chunk_id]
        else:
            item_key = store["item_key"]

        return {
            "item_key": item_key,
            "content": next_chunk,
            "has_more": has_more,
            "chunk_id": chunk_id if has_more else None,
            "current_chunk": store["current"],
            "total_chunks": store["total"],
        }
