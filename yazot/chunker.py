import json
import re
import uuid
from typing import Any

from .exceptions import ZoteroNotFoundError
from .models import ChunkResponse, SearchCollectionResponse, TextChunkResponse, ZoteroItem


class ResponseChunker:
    """Simple response chunking for large results."""

    # Safety margin for response metadata (message, count, chunk_id, etc.)
    # Claude Code tool result limit is ~10000 tokens; default max_chunk_size=5000
    # leaves room for metadata overhead and JSON wrapper.
    METADATA_OVERHEAD = 2000
    MCP_TOKEN_LIMIT = 10000

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
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
        """Estimate tokens for complete response including metadata."""
        items_tokens = self.estimate_tokens([item.model_dump() for item in items])

        if include_metadata:
            return items_tokens + self.METADATA_OVERHEAD

        return items_tokens

    def needs_chunking(self, data: list[ZoteroItem]) -> bool:
        """Check if data needs chunking."""
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

    def build_chunked_response(
        self, items: list[ZoteroItem], total_count: int
    ) -> SearchCollectionResponse:
        """Build a SearchCollectionResponse, chunking if needed."""
        if not self.needs_chunking(items):
            return SearchCollectionResponse(items=items, count=total_count)

        chunk_response = self.chunk_response(items)
        message = None
        if chunk_response.has_more:
            message = (
                f"⚠️ Results chunked ({chunk_response.chunk_info}). "
                f"To get remaining results, call: "
                f"get_next_chunk(chunk_id='{chunk_response.chunk_id}')"
            )

        return SearchCollectionResponse(
            items=chunk_response.items,
            count=total_count,
            has_more=chunk_response.has_more,
            chunk_id=chunk_response.chunk_id,
            current_chunk=chunk_response.current_chunk,
            total_chunks=chunk_response.total_chunks,
            message=message,
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

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.text_store: dict[str, dict[str, Any]] = {}  # In-memory storage

    def estimate_tokens(self, text: str) -> int:
        """Simple token estimation (4 chars = 1 token)."""
        return len(text) // 4

    def needs_chunking(self, text: str) -> bool:
        """Check if text needs chunking."""
        return self.estimate_tokens(text) > self.max_tokens

    def _split_by_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs."""
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_by_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def chunk_text(self, text: str, item_key: str) -> TextChunkResponse:
        """Chunk long text into manageable pieces.

        Returns first chunk with metadata.
        """
        if not text or not text.strip():
            return TextChunkResponse(item_key=item_key, content="")

        total_tokens = self.estimate_tokens(text)

        if total_tokens <= self.max_tokens:
            return TextChunkResponse(item_key=item_key, content=text)

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
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

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
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        if len(chunks) <= 1:
            return TextChunkResponse(item_key=item_key, content=chunks[0] if chunks else text)

        # Store remaining chunks
        chunk_id = str(uuid.uuid4())
        self.text_store[chunk_id] = {
            "item_key": item_key,
            "chunks": chunks[1:],
            "current": 1,
            "total": len(chunks),
        }

        return TextChunkResponse(
            item_key=item_key,
            content=chunks[0],
            has_more=True,
            chunk_id=chunk_id,
            current_chunk=1,
            total_chunks=len(chunks),
        )

    def get_next_text_chunk(self, chunk_id: str) -> TextChunkResponse:
        """Get next text chunk by ID.

        Raises:
            ZoteroNotFoundError: If chunk_id is invalid or expired
        """
        if chunk_id not in self.text_store:
            raise ZoteroNotFoundError("text chunk", chunk_id)

        store = self.text_store[chunk_id]

        if not store["chunks"]:
            item_key = store["item_key"]
            del self.text_store[chunk_id]
            return TextChunkResponse(item_key=item_key, content="")

        next_chunk = store["chunks"].pop(0)
        store["current"] += 1

        has_more = len(store["chunks"]) > 0
        item_key = store["item_key"]
        current = store["current"]
        total = store["total"]

        if not has_more:
            del self.text_store[chunk_id]

        return TextChunkResponse(
            item_key=item_key,
            content=next_chunk,
            has_more=has_more,
            chunk_id=chunk_id if has_more else None,
            current_chunk=current,
            total_chunks=total,
        )
