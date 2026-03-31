"""Tests for TextChunker functionality."""

from yazot.chunker import TextChunker


class TestTextChunker:
    """Test text chunking functionality."""

    def test_text_chunker_no_chunking_needed(self) -> None:
        """Test that short text doesn't get chunked."""
        chunker = TextChunker(max_tokens=1000)

        short_text = "This is a short text that doesn't need chunking."
        result = chunker.chunk_text(short_text, "TEST123")

        assert result.item_key == "TEST123"
        assert result.content == short_text
        assert result.has_more is False
        assert result.chunk_id is None
        assert result.current_chunk is None
        assert result.total_chunks is None

    def test_text_chunker_chunks_long_text(self) -> None:
        """Test that long text gets chunked properly."""
        chunker = TextChunker(max_tokens=50)  # Small chunk size for testing

        # Create text that will need chunking
        long_text = "\n\n".join([f"This is paragraph {i}. " * 20 for i in range(10)])

        result = chunker.chunk_text(long_text, "TEST456")

        assert result.item_key == "TEST456"
        assert result.has_more is True
        assert result.chunk_id is not None
        assert result.current_chunk == 1
        assert result.total_chunks is not None
        assert result.total_chunks > 1
        assert len(result.content) > 0

    def test_text_chunker_get_next_chunk(self) -> None:
        """Test getting next chunk of text."""
        chunker = TextChunker(max_tokens=50)

        long_text = "\n\n".join([f"Paragraph {i}. " * 20 for i in range(10)])

        # Get first chunk
        first_result = chunker.chunk_text(long_text, "TEST789")
        assert first_result.has_more is True

        chunk_id = first_result.chunk_id
        assert chunk_id is not None

        # Get next chunk
        next_result = chunker.get_next_text_chunk(chunk_id)

        assert next_result.item_key == "TEST789"
        assert len(next_result.content) > 0
        assert next_result.current_chunk == 2

    def test_text_chunker_invalid_chunk_id(self) -> None:
        """Test handling of invalid chunk ID raises ZoteroNotFoundError."""
        import pytest

        from yazot.exceptions import ZoteroNotFoundError

        chunker = TextChunker(max_tokens=18000)

        with pytest.raises(ZoteroNotFoundError):
            chunker.get_next_text_chunk("invalid-chunk-id")

    def test_text_chunker_empty_text(self) -> None:
        """Test handling of empty text."""
        chunker = TextChunker(max_tokens=18000)

        result = chunker.chunk_text("", "EMPTY")

        assert result.item_key == "EMPTY"
        assert result.content == ""
        assert result.has_more is False

    def test_text_chunker_splits_by_paragraphs(self) -> None:
        """Test that text is split by paragraphs when possible."""
        chunker = TextChunker(max_tokens=100)

        # Create text with clear paragraph boundaries
        text = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3."

        result = chunker.chunk_text(text, "PARA")

        # Should keep paragraphs together if they fit
        assert "\n\n" in result.content or result.content == text

    def test_text_chunker_complete_workflow(self) -> None:
        """Test complete workflow: chunk and retrieve all parts."""
        chunker = TextChunker(max_tokens=50)

        long_text = "\n\n".join([f"Section {i}. " * 30 for i in range(5)])

        # Get first chunk
        result = chunker.chunk_text(long_text, "WORKFLOW")
        all_content = [result.content]

        # Get all remaining chunks
        while result.has_more:
            result = chunker.get_next_text_chunk(result.chunk_id)
            all_content.append(result.content)

        # Verify we got all the text back
        reconstructed = "\n\n".join(all_content)
        assert "Section 0" in reconstructed
        assert "Section 4" in reconstructed
        # Some whitespace differences are acceptable
        assert len(reconstructed) > len(long_text) * 0.9


class TestTextChunkerBoundary:
    """Test TextChunker with MCP token limit boundary cases."""

    def test_mcp_token_limit_compliance(self) -> None:
        """Test that text chunks stay under MCP's 25000 token limit."""
        chunker = TextChunker(max_tokens=20000)

        # Create very long text that would exceed limits (100K tokens)
        long_text = "This is a sentence. " * 20000  # ~100K tokens

        result = chunker.chunk_text(long_text, "HUGE_TEXT")

        # Check first chunk
        first_chunk_tokens = chunker.estimate_tokens(result.content)
        assert first_chunk_tokens <= 20000, f"First chunk: {first_chunk_tokens} tokens"

        # Check all subsequent chunks
        while result.has_more:
            result = chunker.get_next_text_chunk(result.chunk_id)
            chunk_tokens = chunker.estimate_tokens(result.content)
            assert chunk_tokens <= 20000, f"Chunk {result.current_chunk}: {chunk_tokens} tokens"

    def test_real_world_article_size(self) -> None:
        """Test with realistic academic article size (~10-15K tokens)."""
        chunker = TextChunker(max_tokens=20000)

        # Simulate a typical academic article abstract + full text
        abstract = "Background: " + ("This study investigates. " * 50)
        intro = "\n\n## Introduction\n\n" + ("Research shows that. " * 200)
        methods = "\n\n## Methods\n\n" + ("We conducted analysis using. " * 150)
        results = "\n\n## Results\n\n" + ("Our findings indicate. " * 200)
        discussion = "\n\n## Discussion\n\n" + ("These results suggest. " * 180)
        conclusion = "\n\n## Conclusion\n\n" + ("In summary. " * 50)

        article_text = abstract + intro + methods + results + discussion + conclusion

        # This should be ~10-12K tokens, should NOT need chunking
        result = chunker.chunk_text(article_text, "ARTICLE")

        article_tokens = chunker.estimate_tokens(article_text)
        assert article_tokens < 20000

        assert result.has_more is False
        assert result.content == article_text

    def test_extremely_long_article(self) -> None:
        """Test with very long article that needs multiple chunks."""
        chunker = TextChunker(max_tokens=20000)

        # Create article with 30 sections (each ~5K tokens)
        sections = []
        for i in range(30):
            section = f"\n\n## Section {i}\n\n" + (f"Content for section {i}. " * 1000)
            sections.append(section)

        long_article = "".join(sections)

        result = chunker.chunk_text(long_article, "LONG_ARTICLE")

        # Should need chunking
        assert result.has_more is True
        assert result.total_chunks is not None
        assert result.total_chunks > 1

        # Verify all chunks stay under limit
        all_chunks_valid = True
        current_result = result
        while True:
            tokens = chunker.estimate_tokens(current_result.content)
            if tokens > 20000:
                all_chunks_valid = False
                break

            if not current_result.has_more:
                break

            current_result = chunker.get_next_text_chunk(current_result.chunk_id)

        assert all_chunks_valid, "All chunks should be under token limit"

    def test_exact_boundary_20000_tokens(self) -> None:
        """Test text that is exactly at the 20000 token boundary."""
        chunker = TextChunker(max_tokens=20000)

        # Create text that's exactly 20000 tokens (80000 chars)
        exact_text = "a" * 80000

        result = chunker.chunk_text(exact_text, "EXACT")

        tokens = chunker.estimate_tokens(exact_text)
        assert tokens == 20000

        # Should NOT need chunking at exactly the limit
        assert result.has_more is False

    def test_just_over_boundary(self) -> None:
        """Test text just over boundary with natural split points."""
        chunker = TextChunker(max_tokens=20000)

        # Create text with paragraph breaks so chunker can split
        over_text = "\n\n".join(["Sentence. " * 800 for _ in range(11)])

        tokens = chunker.estimate_tokens(over_text)
        assert tokens > 20000

        result = chunker.chunk_text(over_text, "OVER")

        # Should need chunking
        assert result.has_more is True

    def test_very_long_single_sentence(self) -> None:
        """Test handling of extremely long single sentence (no periods).

        Text without natural split boundaries cannot be chunked further
        and is returned as a single chunk even if it exceeds max_tokens.
        """
        chunker = TextChunker(max_tokens=1000)

        # Create one very long sentence without periods
        long_sentence = "word " * 10000  # ~2500 tokens, no sentence breaks

        result = chunker.chunk_text(long_sentence, "LONG_SENT")

        # Without sentence/paragraph breaks, chunker returns as single chunk
        assert result.content.strip() == long_sentence.strip()
        assert result.item_key == "LONG_SENT"

    def test_paragraph_boundary_preservation(self) -> None:
        """Test that paragraph boundaries are preserved when possible."""
        chunker = TextChunker(max_tokens=500)

        # Create text with clear paragraph boundaries
        paragraphs = []
        for i in range(10):
            para = f"Paragraph {i}. " * 50  # Each paragraph ~100 tokens
            paragraphs.append(para)

        text = "\n\n".join(paragraphs)

        result = chunker.chunk_text(text, "PARAS")

        # First chunk should end at paragraph boundary if possible
        first_content = result.content

        # Should have complete paragraphs (ending with period or newline)
        assert first_content.rstrip().endswith(".") or first_content.endswith("\n")

    def test_mixed_content_with_code_blocks(self) -> None:
        """Test chunking text with code blocks and special formatting."""
        chunker = TextChunker(max_tokens=500)

        text = """
# Article Title

Introduction paragraph with some text.

## Code Example

```python
def example():
    return "This is code"
```

More explanation text here.

## Results

Data analysis shows interesting patterns.

```json
{
    "result": "value"
}
```

Final conclusions.
"""

        result = chunker.chunk_text(text, "MIXED")

        # Should handle the text without errors
        assert result.content is not None
        assert result.item_key == "MIXED"

    def test_unicode_and_special_characters(self) -> None:
        """Test chunking with unicode and special characters."""
        chunker = TextChunker(max_tokens=100)

        text = (
            """
        Тестовый текст на русском языке.

        中文测试文本。

        テストテキスト。

        Special chars: €£¥§±×÷

        Math: ∑∫∂∇⊕⊗

        Emoji: 🔬📊📈🧬
        """
            * 50
        )  # Repeat to make it need chunking

        result = chunker.chunk_text(text, "UNICODE")

        # Should handle unicode without errors
        assert result.item_key == "UNICODE"
        assert len(result.content) > 0

        # Verify all chunks can be retrieved
        while result.has_more:
            result = chunker.get_next_text_chunk(result.chunk_id)
            assert len(result.content) > 0

    def test_empty_paragraphs_handling(self) -> None:
        """Test handling of multiple consecutive empty lines."""
        chunker = TextChunker(max_tokens=100)

        text = "Para 1.\n\n\n\n\n\nPara 2.\n\n\n\nPara 3."

        result = chunker.chunk_text(text, "EMPTY_LINES")

        # Should handle multiple newlines gracefully
        assert result.item_key == "EMPTY_LINES"
        assert result.content is not None

    def test_chunk_reconstruction_accuracy(self) -> None:
        """Test that reconstructed text closely matches original."""
        chunker = TextChunker(max_tokens=500)

        original_text = "\n\n".join(
            [f"Paragraph {i}. " + ("Content here. " * 50) for i in range(20)]
        )

        result = chunker.chunk_text(original_text, "RECONSTRUCT")

        # Collect all chunks
        all_chunks = [result.content]
        while result.has_more:
            result = chunker.get_next_text_chunk(result.chunk_id)
            all_chunks.append(result.content)

        # Reconstruct (with paragraph separators)
        reconstructed = "\n\n".join(all_chunks)

        # Should be very close to original (allowing for minor whitespace differences)
        # Check that all paragraphs are present
        for i in range(20):
            assert f"Paragraph {i}" in reconstructed

        # Length should be similar (within 5%)
        original_len = len(original_text)
        reconstructed_len = len(reconstructed)
        assert abs(reconstructed_len - original_len) / original_len < 0.05
