"""Tests for TextChunker functionality."""

from src.chunker import TextChunker


class TestTextChunker:
    """Test text chunking functionality."""

    def test_text_chunker_no_chunking_needed(self) -> None:
        """Test that short text doesn't get chunked."""
        chunker = TextChunker(max_tokens=1000)

        short_text = "This is a short text that doesn't need chunking."
        result = chunker.chunk_text(short_text, "TEST123")

        assert result["item_key"] == "TEST123"
        assert result["content"] == short_text
        assert result["has_more"] is False
        assert result["chunk_id"] is None
        assert result["current_chunk"] is None
        assert result["total_chunks"] is None

    def test_text_chunker_chunks_long_text(self) -> None:
        """Test that long text gets chunked properly."""
        chunker = TextChunker(max_tokens=50)  # Small chunk size for testing

        # Create text that will need chunking
        long_text = "\n\n".join([f"This is paragraph {i}. " * 20 for i in range(10)])

        result = chunker.chunk_text(long_text, "TEST456")

        assert result["item_key"] == "TEST456"
        assert result["has_more"] is True
        assert result["chunk_id"] is not None
        assert result["current_chunk"] == 1
        assert result["total_chunks"] is not None
        assert result["total_chunks"] > 1
        assert len(result["content"]) > 0

    def test_text_chunker_get_next_chunk(self) -> None:
        """Test getting next chunk of text."""
        chunker = TextChunker(max_tokens=50)

        long_text = "\n\n".join([f"Paragraph {i}. " * 20 for i in range(10)])

        # Get first chunk
        first_result = chunker.chunk_text(long_text, "TEST789")
        assert first_result["has_more"] is True

        chunk_id = first_result["chunk_id"]
        assert chunk_id is not None

        # Get next chunk
        next_result = chunker.get_next_text_chunk(chunk_id)

        assert next_result["item_key"] == "TEST789"
        assert len(next_result["content"]) > 0
        assert next_result["current_chunk"] == 2

    def test_text_chunker_invalid_chunk_id(self) -> None:
        """Test handling of invalid chunk ID."""
        chunker = TextChunker()

        result = chunker.get_next_text_chunk("invalid-chunk-id")

        assert result["error"] == "Invalid or expired chunk ID"
        assert result["has_more"] is False

    def test_text_chunker_empty_text(self) -> None:
        """Test handling of empty text."""
        chunker = TextChunker()

        result = chunker.chunk_text("", "EMPTY")

        assert result["item_key"] == "EMPTY"
        assert result["content"] == ""
        assert result["has_more"] is False

    def test_text_chunker_splits_by_paragraphs(self) -> None:
        """Test that text is split by paragraphs when possible."""
        chunker = TextChunker(max_tokens=100)

        # Create text with clear paragraph boundaries
        text = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3."

        result = chunker.chunk_text(text, "PARA")

        # Should keep paragraphs together if they fit
        assert "\n\n" in result["content"] or result["content"] == text

    def test_text_chunker_complete_workflow(self) -> None:
        """Test complete workflow: chunk and retrieve all parts."""
        chunker = TextChunker(max_tokens=50)

        long_text = "\n\n".join([f"Section {i}. " * 30 for i in range(5)])

        # Get first chunk
        result = chunker.chunk_text(long_text, "WORKFLOW")
        all_content = [result["content"]]

        # Get all remaining chunks
        while result["has_more"]:
            result = chunker.get_next_text_chunk(result["chunk_id"])
            all_content.append(result["content"])

        # Verify we got all the text back
        reconstructed = "\n\n".join(all_content)
        assert "Section 0" in reconstructed
        assert "Section 4" in reconstructed
        # Some whitespace differences are acceptable
        assert len(reconstructed) > len(long_text) * 0.9
