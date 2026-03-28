"""PDF text extraction utility shared across modules."""

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pypdf.

    Args:
        pdf_bytes: Raw PDF file content

    Returns:
        Extracted text with pages joined by double newlines.
        Returns empty string if PDF contains no extractable text (e.g. scanned images).
        Callers should check for empty result and handle accordingly.

    Raises:
        ValueError: If pdf_bytes cannot be parsed as a valid PDF (corrupt, empty, wrong format)
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except (PdfReadError, PdfStreamError) as e:
        raise ValueError(f"Failed to parse PDF: {e}") from e
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n\n".join(text_parts)
