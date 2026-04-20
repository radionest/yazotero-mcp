"""Unit tests for formatting utilities in formatters.py module."""

from yazot.formatters import extract_note_text, format_note_html


class TestFormatNoteHtml:
    """Tests for format_note_html() — markdown to HTML conversion."""

    def test_simple_text(self) -> None:
        result = format_note_html("Hello world")
        assert "<p>Hello world</p>" in result

    def test_paragraphs(self) -> None:
        result = format_note_html("Paragraph 1\n\nParagraph 2")
        assert "<p>Paragraph 1</p>" in result
        assert "<p>Paragraph 2</p>" in result

    def test_heading(self) -> None:
        result = format_note_html("## Key findings")
        assert "<h2>Key findings</h2>" in result

    def test_blockquote(self) -> None:
        result = format_note_html("> This is a quote")
        assert "<blockquote>" in result
        assert "This is a quote" in result

    def test_bold_and_italic(self) -> None:
        result = format_note_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_unordered_list(self) -> None:
        result = format_note_html("- Item 1\n- Item 2")
        assert "<li>Item 1</li>" in result
        assert "<li>Item 2</li>" in result

    def test_escapes_ampersand(self) -> None:
        result = format_note_html("Tom & Jerry")
        assert "&amp;" in result

    def test_empty_string(self) -> None:
        result = format_note_html("")
        assert result == ""


class TestExtractNoteText:
    """Tests for extract_note_text() — HTML to markdown conversion."""

    def test_simple_paragraph(self) -> None:
        result = extract_note_text("<p>Hello world</p>")
        assert "Hello world" in result

    def test_multiple_paragraphs(self) -> None:
        result = extract_note_text("<p>Paragraph 1</p><p>Paragraph 2</p>")
        assert "Paragraph 1" in result
        assert "Paragraph 2" in result

    def test_heading(self) -> None:
        result = extract_note_text("<h2>Key findings</h2>")
        assert "Key findings" in result
        assert "##" in result

    def test_blockquote_to_markdown(self) -> None:
        result = extract_note_text("<blockquote><p>A quoted text</p></blockquote>")
        assert "> " in result
        assert "A quoted text" in result

    def test_bold_and_italic(self) -> None:
        result = extract_note_text("<p>Text with <strong>bold</strong> and <em>italic</em></p>")
        assert "**bold**" in result
        assert "*italic*" in result

    def test_list(self) -> None:
        result = extract_note_text("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert "Item 1" in result
        assert "Item 2" in result

    def test_unescapes_entities(self) -> None:
        result = extract_note_text("<p>Tom &amp; Jerry</p>")
        assert "Tom & Jerry" in result

    def test_empty_html(self) -> None:
        result = extract_note_text("<p></p>")
        assert result == ""

    def test_complex_html(self) -> None:
        html = """
        <h1>Title</h1>
        <p>First paragraph with <a href="#">link</a></p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
        """
        result = extract_note_text(html)
        assert "Title" in result
        assert "Item 1" in result
        assert "Item 2" in result

    def test_nested_tags(self) -> None:
        result = extract_note_text("<div><div><p>Deep content</p></div></div>")
        assert "Deep content" in result


class TestRoundtrip:
    """Tests that markdown → HTML → markdown preserves key elements."""

    def test_blockquote_survives_roundtrip(self) -> None:
        md_text = "Some text\n\n> This is a quoted passage\n\nMore text"
        html = format_note_html(md_text)
        result = extract_note_text(html)
        assert "> " in result
        assert "This is a quoted passage" in result

    def test_heading_survives_roundtrip(self) -> None:
        md_text = "# Title\n\n## Section"
        html = format_note_html(md_text)
        result = extract_note_text(html)
        assert "# Title" in result
        assert "## Section" in result

    def test_list_survives_roundtrip(self) -> None:
        md_text = "- Point one\n- Point two"
        html = format_note_html(md_text)
        result = extract_note_text(html)
        assert "Point one" in result
        assert "Point two" in result
