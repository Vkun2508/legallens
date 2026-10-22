"""Document ingestion and text cleaning.

Supports plain-text files and text-based PDFs (PDF needs the optional `pypdf`
package). Cleaning removes extraction artefacts but keeps line breaks, blank
lines and numbering, because the segmenter relies on them.
"""

from __future__ import annotations

import re
from pathlib import Path

# Lines that are only page furniture: "3", "- 3 -", "Page 3", "Page 3 of 10".
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:-\s*\d+\s*-|(?:page\s+)?\d+(?:\s+of\s+\d+)?)\s*$", re.I)
# Word broken across lines by a hyphen, e.g. "agree-\nment". Only joined when
# both sides are lowercase, so real compounds like "Third-\nParty" survive.
_HYPHEN_BREAK_RE = re.compile(r"([a-z])-\n([a-z])")


def load_document(path: str | Path) -> str:
    """Read a .txt/.md or text-based .pdf file and return normalized text."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raw = _extract_pdf_text(path)
    elif suffix in {".txt", ".md", ""}:
        raw = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {suffix} (expected .txt, .md or .pdf)")
    return normalize_text(raw)


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError("PDF support needs pypdf: pip install pypdf") from exc
    reader = PdfReader(path)
    # Separate pages with a blank line so a page break never glues two clauses.
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def normalize_text(text: str) -> str:
    """Clean extracted text while preserving the structure segmentation needs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    text = text.replace(" ", " ").replace("­", "")  # nbsp, soft hyphen
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"[“”]", '"', text)

    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if _PAGE_NUMBER_RE.match(line):
            line = ""
        lines.append(line)
    text = "\n".join(lines)

    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
