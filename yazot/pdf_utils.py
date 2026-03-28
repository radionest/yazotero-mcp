"""PDF text extraction utility shared across modules."""

import io

from pypdf import PdfReader


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pypdf.

    Args:
        pdf_bytes: Raw PDF file content

    Returns:
        Extracted text with pages joined by double newlines.
        Empty string if no text could be extracted.

    Raises:
        ValueError: If pdf_bytes cannot be parsed as a valid PDF
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {e}") from e
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n\n".join(text_parts)
