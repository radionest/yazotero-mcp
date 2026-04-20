"""Formatting utilities for note content conversion."""

import html
from collections.abc import Sequence
from datetime import datetime

import markdown as md
import markdownify
from bs4 import BeautifulSoup, Tag

type NoteData = dict[str, str | int | float | Sequence[str | int | float | NoteData] | NoteData]


def format_note_html(text: str) -> str:
    """Convert markdown text to HTML for Zotero notes."""
    return md.markdown(text, extensions=["extra"])


def extract_note_text(html_content: str) -> str:
    """Convert HTML note back to readable markdown."""
    result: str = markdownify.markdownify(html_content, heading_style="ATX")
    return result.strip()


def parse_datetime(date_str: str) -> datetime:
    """Parse datetime string from Zotero."""
    if not date_str:
        return datetime.now()

    try:
        # Try ISO format first
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        # Fallback to current time if parsing fails
        return datetime.now()


def format_dict_to_html(data: NoteData, level: int = 1) -> str:
    """Convert dictionary to HTML with keys as headers (capitalized).

    Args:
        data: Dictionary to convert
        level: Starting header level (1-6)

    Returns:
        HTML string with nested structure
    """
    html_parts = []

    for key, value in data.items():
        # Convert key to readable header
        header_text = str(key).replace("_", " ").title()
        header_level = min(level, 6)  # HTML only has h1-h6
        html_parts.append(f"<h{header_level}>{html.escape(header_text)}</h{header_level}>")

        match value:
            case dict():
                html_parts.append(format_dict_to_html(value, level + 1))
            case list():
                # Format list
                html_parts.append("<ul>")
                for item in value:
                    if isinstance(item, dict):
                        html_parts.append("<li>")
                        html_parts.append(format_dict_to_html(item, level + 1))
                        html_parts.append("</li>")
                    else:
                        html_parts.append(f"<li>{html.escape(str(item))}</li>")
                html_parts.append("</ul>")
            case _:
                # Simple value as paragraph
                html_parts.append(f"<p>{html.escape(str(value))}</p>")

    return "".join(html_parts)


def parse_html_to_dict(html_content: str) -> NoteData:
    """Parse HTML with headers back into dictionary structure.

    Args:
        html_content: HTML string with header-based structure

    Returns:
        Dictionary with nested structure
    """
    soup = BeautifulSoup(html_content, "html.parser")
    result: NoteData = {}
    stack: list[tuple[int, NoteData]] = [(0, result)]  # (level, dict)

    # Get all top-level elements
    for element in soup.children:
        if not isinstance(element, Tag):
            continue

        match element.name:
            case "h1" | "h2" | "h3" | "h4" | "h5" | "h6":
                level = int(element.name[1])
                key = element.get_text().strip().lower().replace(" ", "_")

                # Adjust stack to current level
                while stack and stack[-1][0] >= level:
                    stack.pop()

                if not stack:
                    stack.append((0, result))

                parent_dict = stack[-1][1]

                # Collect content until next header
                content_elements: list[Tag] = []
                for sibling in element.next_siblings:
                    if isinstance(sibling, Tag) and sibling.name in {
                        "h1",
                        "h2",
                        "h3",
                        "h4",
                        "h5",
                        "h6",
                    }:
                        break
                    if isinstance(sibling, Tag):
                        content_elements.append(sibling)

                # Parse content based on type
                match content_elements:
                    case []:
                        parent_dict[key] = ""
                    case [Tag(name="ul" | "ol") as list_elem]:
                        parent_dict[key] = _parse_list(list_elem)
                    case [Tag(name="p") as para]:
                        parent_dict[key] = para.get_text().strip()
                    case [*elements] if any(
                        isinstance(e, Tag) and e.name.startswith("h") for e in elements
                    ):
                        # Has nested headers - create nested dict
                        nested_dict: NoteData = {}
                        parent_dict[key] = nested_dict
                        stack.append((level, nested_dict))
                    case [*elements]:
                        # Multiple elements - combine text
                        texts = [e.get_text().strip() for e in elements if isinstance(e, Tag)]
                        parent_dict[key] = " ".join(t for t in texts if t)

    return result


def _parse_list(list_element: Tag) -> Sequence[str]:
    """Parse ul/ol element into list of strings.

    Args:
        list_element: BeautifulSoup Tag for ul or ol

    Returns:
        List of text items
    """
    items: list[str] = []
    for li in list_element.find_all("li", recursive=False):
        match li:
            case Tag():
                items.append(li.get_text().strip())
    return items
