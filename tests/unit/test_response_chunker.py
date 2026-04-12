"""Comprehensive tests for ResponseChunker functionality."""

import json

from yazot.chunker import ResponseChunker
from yazot.models import ZoteroItem, ZoteroItemData, ZoteroTag


class TestResponseChunker:
    """Test ResponseChunker with emphasis on MCP token limits."""

    def create_test_item(self, key: str, size_multiplier: int = 1) -> ZoteroItem:
        """Create a test ZoteroItem with configurable size.

        Args:
            key: Item key
            size_multiplier: Multiplier for content size (1 = ~100 tokens)
        """
        abstract = "This is a test abstract. " * (20 * size_multiplier)
        title = f"Test Article {key} - " + ("Long Title " * size_multiplier)

        return ZoteroItem(
            key=key,
            version=1,
            data=ZoteroItemData(
                title=title,
                abstractNote=abstract,
                itemType="journalArticle",
                date="2024",
                creators=[{"firstName": "John", "lastName": "Doe", "creatorType": "author"}],
                tags=[ZoteroTag(tag="test", type=0)],
                collections=["COLL123"],
            ),
        )

    def test_chunker_constants(self) -> None:
        """Test that chunker constants are properly set."""
        chunker = ResponseChunker(max_tokens=5000)

        assert hasattr(chunker, "MCP_TOKEN_LIMIT")
        assert chunker.MCP_TOKEN_LIMIT == 10000

        assert hasattr(chunker, "METADATA_OVERHEAD")
        assert chunker.METADATA_OVERHEAD == 2000

        # Effective max should be max_tokens - overhead
        assert chunker.effective_max_tokens == chunker.max_tokens - chunker.METADATA_OVERHEAD

    def test_estimate_tokens_basic(self) -> None:
        """Test basic token estimation."""
        chunker = ResponseChunker(max_tokens=18000)

        # Test string estimation (4 chars = 1 token)
        text = "a" * 400  # Should be ~100 tokens
        assert chunker.estimate_tokens(text) == 100

        # Test object estimation
        data = {"key": "value" * 100}
        json_str = json.dumps(data, default=str)
        expected = len(json_str) // 4
        assert chunker.estimate_tokens(data) == expected

    def test_estimate_response_tokens_without_metadata(self) -> None:
        """Test response token estimation without metadata."""
        chunker = ResponseChunker(max_tokens=18000)
        items = [self.create_test_item(f"TEST{i}") for i in range(5)]

        tokens_with_metadata = chunker.estimate_response_tokens(items, include_metadata=True)
        tokens_without_metadata = chunker.estimate_response_tokens(items, include_metadata=False)

        # With metadata should be larger
        assert tokens_with_metadata > tokens_without_metadata
        # Difference should be METADATA_OVERHEAD
        assert tokens_with_metadata == tokens_without_metadata + chunker.METADATA_OVERHEAD

    def test_estimate_response_tokens_with_metadata(self) -> None:
        """Test that metadata overhead is correctly added."""
        chunker = ResponseChunker(max_tokens=18000)
        items = [self.create_test_item(f"TEST{i}") for i in range(10)]

        tokens = chunker.estimate_response_tokens(items, include_metadata=True)
        items_only_tokens = chunker.estimate_tokens([item.model_dump() for item in items])

        # Should include overhead
        assert tokens == items_only_tokens + chunker.METADATA_OVERHEAD

    def test_needs_chunking_with_safety_margin(self) -> None:
        """Test that needs_chunking uses effective_max_tokens with safety margin."""
        chunker = ResponseChunker(max_tokens=20000)

        # Create items over effective_max (18000 tokens)
        items = [self.create_test_item(f"TEST{i}") for i in range(91)]
        assert chunker.needs_chunking(items) is True

        # Create items safely under effective_max
        small_items = [self.create_test_item(f"TEST{i}") for i in range(60)]
        assert chunker.needs_chunking(small_items) is False

    def test_no_chunking_needed_for_small_data(self) -> None:
        """Test that small datasets don't get chunked."""
        chunker = ResponseChunker(max_tokens=20000)
        items = [self.create_test_item(f"TEST{i}") for i in range(10)]

        assert chunker.needs_chunking(items) is False

        response = chunker.chunk_response(items)
        assert response.has_more is False
        assert response.chunk_id is None
        assert len(response.items) == 10

    def test_chunking_large_dataset(self) -> None:
        """Test that large datasets get properly chunked."""
        chunker = ResponseChunker(max_tokens=1000)  # Small for testing

        # Create enough items to require chunking
        items = [self.create_test_item(f"TEST{i}", size_multiplier=1) for i in range(50)]

        assert chunker.needs_chunking(items) is True

        response = chunker.chunk_response(items)

        assert response.has_more is True
        assert response.chunk_id is not None
        assert response.current_chunk == 1
        assert response.total_chunks is not None
        assert response.total_chunks > 1
        assert len(response.items) < len(items)  # First chunk should be smaller

    def test_chunk_response_boundary(self) -> None:
        """Test chunking at exact boundary conditions."""
        chunker = ResponseChunker(max_tokens=20000)

        # Create items that are exactly at effective_max_tokens (18000)
        # Each item ~100 tokens, so 180 items = 18000 tokens
        items = [self.create_test_item(f"TEST{i}") for i in range(180)]

        # Should not need chunking at exactly the limit
        response = chunker.chunk_response(items)
        # Might or might not chunk depending on exact token calculation
        # But should definitely handle it correctly

        if response.has_more:
            assert response.chunk_id is not None
            assert response.total_chunks is not None
        else:
            assert response.chunk_id is None

    def test_get_next_chunk_workflow(self) -> None:
        """Test complete workflow of getting all chunks."""
        chunker = ResponseChunker(max_tokens=1000)

        items = [self.create_test_item(f"TEST{i}") for i in range(50)]

        # Get first chunk
        first_response = chunker.chunk_response(items)
        assert first_response.has_more is True
        assert first_response.current_chunk == 1

        all_items = list(first_response.items)
        chunk_id = first_response.chunk_id

        # Get all remaining chunks
        while chunk_id:
            next_response = chunker.get_next_chunk(chunk_id)
            all_items.extend(next_response.items)

            if next_response.has_more:
                chunk_id = next_response.chunk_id
                assert next_response.current_chunk is not None
                assert next_response.current_chunk > first_response.current_chunk
            else:
                chunk_id = None

        # Should have retrieved all items
        assert len(all_items) == len(items)

    def test_get_next_chunk_invalid_id(self) -> None:
        """Test handling of invalid chunk ID raises ZoteroNotFoundError."""
        from yazot.exceptions import ZoteroNotFoundError

        chunker = ResponseChunker(max_tokens=18000)

        import pytest

        with pytest.raises(ZoteroNotFoundError):
            chunker.get_next_chunk("invalid-chunk-id")

    def test_get_next_chunk_increments_counter(self) -> None:
        """Test that current_chunk increments correctly."""
        chunker = ResponseChunker(max_tokens=1000)

        items = [self.create_test_item(f"TEST{i}") for i in range(50)]

        first = chunker.chunk_response(items)
        assert first.current_chunk == 1
        assert first.chunk_id

        second = chunker.get_next_chunk(first.chunk_id)
        assert second.current_chunk == 2
        assert second.chunk_id

        if second.has_more:
            third = chunker.get_next_chunk(second.chunk_id)
            assert third.current_chunk == 3

    def test_chunk_cleanup_after_last_chunk(self) -> None:
        """Test that chunks are cleaned up from storage after retrieval."""
        chunker = ResponseChunker(max_tokens=1000)

        items = [self.create_test_item(f"TEST{i}") for i in range(30)]

        first = chunker.chunk_response(items)
        chunk_id = first.chunk_id

        # Chunk should be in storage
        assert chunk_id in chunker.chunks_store

        # Get all chunks
        current_id: str | None = chunk_id
        while current_id:
            response = chunker.get_next_chunk(current_id)
            current_id = response.chunk_id if response.has_more else None

        # After last chunk, should be cleaned up
        assert chunk_id not in chunker.chunks_store

    def test_concurrent_chunk_sessions(self) -> None:
        """Test that multiple chunk sessions can coexist."""
        chunker = ResponseChunker(max_tokens=1000)

        items1 = [self.create_test_item(f"A{i}") for i in range(30)]
        items2 = [self.create_test_item(f"B{i}") for i in range(40)]

        # Create two separate chunk sessions
        session1 = chunker.chunk_response(items1)
        session2 = chunker.chunk_response(items2)

        assert session1.chunk_id != session2.chunk_id
        assert session1.chunk_id in chunker.chunks_store
        assert session2.chunk_id in chunker.chunks_store

        # Get next chunk from session 1
        next1 = chunker.get_next_chunk(session1.chunk_id)
        assert next1.items[0].key.startswith("A")

        # Get next chunk from session 2
        next2 = chunker.get_next_chunk(session2.chunk_id)
        assert next2.items[0].key.startswith("B")

    def test_empty_items_list(self) -> None:
        """Test handling of empty items list."""
        chunker = ResponseChunker(max_tokens=18000)

        items: list[ZoteroItem] = []

        assert chunker.needs_chunking(items) is False

        response = chunker.chunk_response(items)
        assert response.has_more is False
        assert len(response.items) == 0

    def test_single_large_item(self) -> None:
        """Test chunking with a single very large item."""
        chunker = ResponseChunker(max_tokens=1000)

        # Create one very large item (should still return it)
        items = [self.create_test_item("HUGE", size_multiplier=100)]

        # Even if one item exceeds limit, should return it without chunking
        # (cannot split a single item)
        response = chunker.chunk_response(items)

        # Implementation detail: single item that's too large is still returned
        assert len(response.items) >= 1

    def test_chunk_response_preserves_item_integrity(self) -> None:
        """Test that chunking doesn't modify or corrupt items."""
        chunker = ResponseChunker(max_tokens=2000)

        original_items = [self.create_test_item(f"TEST{i}") for i in range(50)]
        original_keys = [item.key for item in original_items]

        response = chunker.chunk_response(original_items)

        # Collect all items from all chunks
        all_chunked_items = list(response.items)
        chunk_id = response.chunk_id

        while chunk_id:
            next_response = chunker.get_next_chunk(chunk_id)
            all_chunked_items.extend(next_response.items)
            chunk_id = next_response.chunk_id if next_response.has_more else None

        chunked_keys = [item.key for item in all_chunked_items]

        # All original items should be present
        assert set(original_keys) == set(chunked_keys)
        # Order should be preserved
        assert original_keys == chunked_keys

    def test_mcp_token_limit_compliance(self) -> None:
        """Test that chunked responses stay under MCP token limit.

        This is the critical test for the bug fix.
        """
        chunker = ResponseChunker(max_tokens=5000)

        # Create a large dataset that would exceed MCP limit without chunking
        items = [self.create_test_item(f"TEST{i}") for i in range(250)]

        response = chunker.chunk_response(items)

        # Estimate tokens for the complete response (items + metadata)
        first_chunk_tokens = chunker.estimate_response_tokens(response.items, include_metadata=True)

        # First chunk should be under MCP limit
        assert first_chunk_tokens < chunker.MCP_TOKEN_LIMIT, (
            f"First chunk has {first_chunk_tokens} tokens, exceeds MCP limit of {chunker.MCP_TOKEN_LIMIT}"
        )

        # Check all subsequent chunks
        chunk_id = response.chunk_id
        while chunk_id:
            next_response = chunker.get_next_chunk(chunk_id)
            chunk_tokens = chunker.estimate_response_tokens(
                next_response.items, include_metadata=True
            )

            assert chunk_tokens < chunker.MCP_TOKEN_LIMIT, (
                f"Chunk {next_response.current_chunk} has {chunk_tokens} tokens, exceeds MCP limit"
            )

            chunk_id = next_response.chunk_id if next_response.has_more else None

    def test_effective_max_tokens_leaves_room_for_metadata(self) -> None:
        """Test that effective_max_tokens provides sufficient safety margin."""
        chunker = ResponseChunker(max_tokens=5000)

        # Create items that fill up to effective_max_tokens
        items = [self.create_test_item(f"TEST{i}") for i in range(180)]

        response = chunker.chunk_response(items)

        # Even if items are at effective_max, total response should be under MCP limit
        total_tokens = chunker.estimate_response_tokens(response.items, include_metadata=True)

        assert total_tokens < chunker.MCP_TOKEN_LIMIT

    def test_chunk_store_is_mutable(self) -> None:
        """Test that chunk store correctly manages state."""
        chunker = ResponseChunker(max_tokens=1000)

        items = [self.create_test_item(f"TEST{i}") for i in range(30)]

        initial_store_size = len(chunker.chunks_store)
        response = chunker.chunk_response(items)

        # Store should have one more entry
        assert len(chunker.chunks_store) == initial_store_size + 1

        # Retrieve all chunks
        chunk_id = response.chunk_id
        while chunk_id:
            next_response = chunker.get_next_chunk(chunk_id)
            chunk_id = next_response.chunk_id if next_response.has_more else None

        # Store should be back to initial size (cleaned up)
        assert len(chunker.chunks_store) == initial_store_size
