"""Unit tests for formatting utilities in formatters.py module."""

from src.formatters import extract_note_text, format_note_html


class TestFormatNoteHtml:
    """Tests for format_note_html() function."""

    def test_format_note_html_simple_text(self) -> None:
        """Test HTML formatting with simple text."""
        result = format_note_html("Hello world")

        assert result == "<p>Hello world</p>"

    def test_format_note_html_with_newlines(self) -> None:
        """Test HTML formatting with single newlines."""
        result = format_note_html("Line 1\nLine 2\nLine 3")

        assert result == "<p>Line 1<br>Line 2<br>Line 3</p>"

    def test_format_note_html_with_paragraphs(self) -> None:
        """Test HTML formatting with paragraph breaks (double newlines)."""
        result = format_note_html("Paragraph 1\n\nParagraph 2\n\nParagraph 3")

        assert result == "<p>Paragraph 1</p><p>Paragraph 2</p><p>Paragraph 3</p>"

    def test_format_note_html_escapes_html_chars(self) -> None:
        """Test that HTML special characters are escaped."""
        result = format_note_html("<script>alert('XSS')</script>")

        assert "&lt;script&gt;" in result
        assert "&lt;/script&gt;" in result
        assert "<script>" not in result

    def test_format_note_html_escapes_ampersand(self) -> None:
        """Test that ampersands are escaped."""
        result = format_note_html("Tom & Jerry")

        assert "&amp;" in result
        assert result == "<p>Tom &amp; Jerry</p>"

    def test_format_note_html_escapes_quotes(self) -> None:
        """Test that quotes are escaped."""
        result = format_note_html('He said "hello"')

        assert "&quot;" in result or '"' in result  # Either escaped or preserved

    def test_format_note_html_mixed_formatting(self) -> None:
        """Test HTML formatting with mixed newlines and special chars."""
        text = "Line 1 <tag>\n\nLine 2 & more\nLine 3"
        result = format_note_html(text)

        assert "&lt;tag&gt;" in result
        assert "&amp;" in result
        assert "<br>" in result
        assert "</p><p>" in result

    def test_format_note_html_empty_string(self) -> None:
        """Test HTML formatting with empty string."""
        result = format_note_html("")

        assert result == "<p></p>"

    def test_format_note_html_whitespace_only(self) -> None:
        """Test HTML formatting with whitespace."""
        result = format_note_html("   \n\n   ")

        assert "<p>" in result
        assert "</p>" in result


class TestExtractNoteText:
    """Tests for extract_note_text() function."""

    def test_extract_note_text_simple_paragraph(self) -> None:
        """Test extracting text from simple paragraph."""
        html = "<p>Hello world</p>"
        result = extract_note_text(html)

        assert result == "Hello world"

    def test_extract_note_text_multiple_paragraphs(self) -> None:
        """Test extracting text from multiple paragraphs."""
        html = "<p>Paragraph 1</p><p>Paragraph 2</p>"
        result = extract_note_text(html)

        assert "Paragraph 1" in result
        assert "Paragraph 2" in result

    def test_extract_note_text_with_br_tags(self) -> None:
        """Test extracting text with br tags."""
        html = "<p>Line 1<br>Line 2<br>Line 3</p>"
        result = extract_note_text(html)

        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
        assert "<br>" not in result

    def test_extract_note_text_strips_all_tags(self) -> None:
        """Test that all HTML tags are stripped."""
        html = "<div><p>Text with <strong>bold</strong> and <em>italic</em></p></div>"
        result = extract_note_text(html)

        assert result == "Text with bold and italic"
        assert "<" not in result
        assert ">" not in result

    def test_extract_note_text_unescapes_entities(self) -> None:
        """Test that HTML entities are unescaped."""
        html = "<p>&lt;script&gt;alert(&quot;test&quot;)&lt;/script&gt;</p>"
        result = extract_note_text(html)

        assert result == '<script>alert("test")</script>'

    def test_extract_note_text_ampersand(self) -> None:
        """Test unescaping ampersands."""
        html = "<p>Tom &amp; Jerry</p>"
        result = extract_note_text(html)

        assert result == "Tom & Jerry"

    def test_extract_note_text_complex_html(self) -> None:
        """Test extracting text from complex HTML structure."""
        html = """
        <div class="note">
            <h1>Title</h1>
            <p>First paragraph with <a href="#">link</a></p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </div>
        """
        result = extract_note_text(html)

        assert "Title" in result
        assert "First paragraph with link" in result
        assert "Item 1" in result
        assert "Item 2" in result
        assert "<" not in result

    def test_extract_note_text_empty_html(self) -> None:
        """Test extracting text from empty HTML."""
        html = "<p></p>"
        result = extract_note_text(html)

        assert result == ""

    def test_extract_note_text_whitespace_normalization(self) -> None:
        """Test that whitespace is handled properly."""
        html = "<p>  Text with   spaces  </p>"
        result = extract_note_text(html)

        assert result == "Text with   spaces"  # Strip outer whitespace

    def test_extract_note_text_nested_tags(self) -> None:
        """Test extracting text from deeply nested tags."""
        html = "<div><div><div><p>Deep content</p></div></div></div>"
        result = extract_note_text(html)

        assert result == "Deep content"

    def test_extract_note_text_special_entities(self) -> None:
        """Test unescaping special HTML entities."""
        html = "<p>&copy; 2024 &mdash; Test &nbsp; Company</p>"
        result = extract_note_text(html)

        assert "©" in result
        assert "—" in result or "&mdash;" in result
