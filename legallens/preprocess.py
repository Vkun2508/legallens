"""Document ingestion and text cleaning.

Supports plain-text files and text-based PDFs (PDF needs the optional `pypdf`
package). Cleaning removes extraction artefacts but keeps line breaks, blank
lines and numbering, because the segmenter relies on them.
"""

from __future__ import annotations

import re
from collections import Counter
from io import BytesIO
from pathlib import Path

# Lines that are only page furniture: "3", "- 3 -", "Page 3", "Page 3 of 10".
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:-\s*\d+\s*-|(?:page\s+)?\d+(?:\s+of\s+\d+)?)\s*$", re.I)
# Word broken across lines by a hyphen, e.g. "agree-\nment". Only joined when
# both sides are lowercase, so real compounds like "Third-\nParty" survive.
_HYPHEN_BREAK_RE = re.compile(r"([a-z])-\n([a-z])")
# Glyphs some PDF fonts extract as control characters (e.g. section numbers as NUL).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
# What is left of a numbered line whose digits were lost: ". Privacy".
_ORPHAN_MARKER_RE = re.compile(r"^[.)]\s+(?=\S)")
_MIN_PAGES_FOR_RUNNING_LINES = 3
_EDGE_LINES = 2


def load_document(path: str | Path) -> str:
    """Read a .txt/.md or text-based .pdf file and return normalized text."""
    path = Path(path)
    return load_bytes(path.read_bytes(), path.suffix)


def load_bytes(data: bytes, suffix: str) -> str:
    """Return normalized text from file contents, e.g. an upload held in memory.

    `suffix` (".pdf", ".txt" or ".md") gives the file type.
    """
    suffix = suffix.lower()
    if suffix == ".pdf":
        raw = _extract_pdf_text(data)
    elif suffix in {".txt", ".md", ""}:
        raw = data.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {suffix} (expected .txt, .md or .pdf)")
    return normalize_text(raw)


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError("PDF support needs pypdf: pip install pypdf") from exc
    reader = PdfReader(BytesIO(data))
    pages = strip_running_lines([page.extract_text() or "" for page in reader.pages])
    # Separate pages with a blank line; the segmenter treats a blank line after
    # an unfinished sentence as a page break rather than a paragraph break.
    return "\n\n".join(pages)


def strip_running_lines(pages: list[str]) -> list[str]:
    """Remove running headers/footers: lines repeated at the top or bottom of most pages."""
    if len(pages) < _MIN_PAGES_FOR_RUNNING_LINES:
        return pages
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({_running_key(line) for line in _edge_lines(page)})
    threshold = max(_MIN_PAGES_FOR_RUNNING_LINES, len(pages) // 2)
    repeated = {key for key, n in counts.items() if n >= threshold}

    cleaned = []
    for page in pages:
        edges = set(_edge_lines(page))
        cleaned.append(
            "\n".join(
                line
                for line in page.split("\n")
                if not (line.strip() in edges and _running_key(line) in repeated)
            )
        )
    return cleaned


def _edge_lines(page: str) -> list[str]:
    lines = [line.strip() for line in page.split("\n") if line.strip()]
    return lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]


def _running_key(line: str) -> str:
    # Digits vary across pages ("Page 3", "Terms - 4"), so compare without them.
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def normalize_text(text: str) -> str:
    """Clean extracted text while preserving the structure segmentation needs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    text = text.replace(" ", " ").replace("­", "")  # nbsp, soft hyphen
    text = _CONTROL_RE.sub("", text)
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"[“”]", '"', text)

    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        line = _ORPHAN_MARKER_RE.sub("", line)
        if _PAGE_NUMBER_RE.match(line):
            line = ""
        lines.append(line)
    text = "\n".join(lines)

    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
