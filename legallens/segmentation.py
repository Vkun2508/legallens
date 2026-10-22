"""Rule-based clause segmentation baseline (paper Sec. V-B).

Splits normalized agreement text into clauses using document structure only:

* numbered lines ("1.", "2.1", "3)", "IV.", "Section 4", "Article 2.3", "§ 5")
  start a new clause;
* headings, numbered ("2. Fees") or not ("PRIVACY", "Payment Terms"), close
  the current clause and become the heading of the clauses that follow;
* in unnumbered text, each paragraph (blank-line separated) is a clause;
* sub-items such as "(a)", "(ii)" and bullets stay inside their parent clause.

A numbered line or heading is only accepted at a plausible boundary (start of
text, after a blank line, after a heading, or after a line ending a sentence),
which stops wrapped lines like "...within\\n30. days" being split.

Known limitations, kept as baseline behaviour for error analysis:
* sentence-case headings directly followed by text ("Payment terms\\nYou...")
  are kept as clause text unless a blank line or numbered line follows;
* in PDFs without blank lines, unnumbered paragraphs under one heading merge;
* numbered lists inside a clause ("1) The Customer...") are split out;
* short standalone lines like "Last updated: 1 March 2026" are taken as headings.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass, field


@dataclass
class Clause:
    """One segmented clause.

    `text` is the clause body with the number prefix removed and wrapped lines
    joined. `start`/`end` are character offsets of the clause's span in the
    input text, including the number prefix, for boundary-level evaluation.
    """

    index: int
    text: str
    number: str | None
    heading: str | None
    start: int
    end: int

    def to_dict(self) -> dict:
        return asdict(self)


_NUMBERED_RE = re.compile(
    r"""^
    (?:
        (?:(?i:section|article|clause)\s+|§\s*)(?P<kw>\d+(?:\.\d+)*|[IVXLC]+)\.?  # Section 4, Article IV
      | (?P<dec>\d{1,3}(?:\.\d{1,3})+)\.?                                         # 2.1, 2.1.3
      | (?P<top>\d{1,3})[.)]                                                       # 2. or 2)
      | (?P<roman>[IVXLC]{1,6})\.                                                  # IV.
    )
    (?:[\s:\-\u2013\u2014]+(?P<rest>.*))?$""",
    re.X,
)
_SUBITEM_RE = re.compile(r"^(?:\(?(?:[a-z]|[ivx]+)\)|[\u2022\u00b7*\-])\s")
_ENDS_SENTENCE_RE = re.compile(r"[.;:!?][\"')\]]*$")
_HEADING_END_PUNCT = (".", ",", ";", ":", "!", "?")
_MAX_HEADING_CHARS = 80
_MAX_HEADING_WORDS = 10
# Pasted web text often has one paragraph per line and no blank lines; PDF
# extraction wraps lines at ~60-100 chars. Longer median lines mean the former.
_PARAGRAPH_LINE_MIN_MEDIAN = 120


@dataclass
class _Line:
    start: int
    end: int
    text: str


@dataclass
class _Draft:
    number: str | None
    heading: str | None
    start: int
    end: int
    parts: list[str] = field(default_factory=list)

    def add(self, line: _Line, text: str, new_paragraph: bool) -> None:
        if self.parts:
            self.parts.append("\n" if new_paragraph else " ")
        self.parts.append(text)
        self.end = line.end


def segment(text: str) -> list[Clause]:
    """Split agreement text (ideally from `normalize_text`) into clauses."""
    lines = _split_lines(text)
    paragraph_per_line = _line_breaks_are_paragraphs(lines)

    clauses: list[Clause] = []
    draft: _Draft | None = None
    ctx_number: str | None = None
    ctx_heading: str | None = None
    prev_kind: str | None = None
    prev_text = ""
    after_blank = True

    def close() -> None:
        nonlocal draft
        if draft is not None and draft.parts:
            body = "".join(draft.parts).strip()
            clauses.append(
                Clause(len(clauses), body, draft.number, draft.heading, draft.start, draft.end)
            )
        draft = None

    for i, line in enumerate(lines):
        if not line.text:
            after_blank = True
            continue

        at_boundary = (
            after_blank
            or paragraph_per_line
            or prev_kind in ("heading", "numbered_heading")
            or bool(_ENDS_SENTENCE_RE.search(prev_text))
        )
        next_text = lines[i + 1].text if i + 1 < len(lines) else ""
        kind, number, body = _classify(line.text, at_boundary, next_text)

        if kind == "numbered_heading":
            close()
            ctx_number, ctx_heading = number, body or None
        elif kind == "heading":
            close()
            if prev_kind == "numbered_heading" and ctx_heading is None:
                ctx_heading = body  # "Section 4" on one line, its title on the next
            else:
                ctx_number, ctx_heading = None, body
        elif kind == "numbered":
            close()
            if ctx_number is not None and not _is_within(number, ctx_number):
                ctx_number, ctx_heading = None, None
            draft = _Draft(number, ctx_heading, line.start, line.end)
            draft.add(line, body, new_paragraph=False)
        else:
            starts_paragraph = after_blank or paragraph_per_line
            if draft is None or (draft.number is None and starts_paragraph):
                close()
                # Body directly under "2. Fees" (or "Section 4" + title) is clause 2.
                number = ctx_number if prev_kind in ("heading", "numbered_heading") else None
                draft = _Draft(number, ctx_heading, line.start, line.end)
            draft.add(line, body, new_paragraph=starts_paragraph or bool(_SUBITEM_RE.match(body)))

        prev_kind, prev_text, after_blank = kind, line.text, False

    close()
    return clauses


def _split_lines(text: str) -> list[_Line]:
    lines = []
    pos = 0
    for raw in text.split("\n"):
        stripped = raw.strip()
        start = pos + (len(raw) - len(raw.lstrip()))
        lines.append(_Line(start, start + len(stripped), stripped))
        pos += len(raw) + 1
    return lines


def _line_breaks_are_paragraphs(lines: list[_Line]) -> bool:
    non_blank = [len(line.text) for line in lines if line.text]
    if len(non_blank) < 2 or len(non_blank) != len(lines):
        return False
    return statistics.median(non_blank) >= _PARAGRAPH_LINE_MIN_MEDIAN


def _classify(text: str, at_boundary: bool, next_text: str) -> tuple[str, str | None, str]:
    """Return (kind, number, body) for a non-blank line."""
    if at_boundary:
        numbered = _match_number(text)
        if numbered:
            number, rest = numbered
            if not rest or _is_heading(rest, next_text):
                return "numbered_heading", number, rest
            return "numbered", number, rest
        if _is_heading(text, next_text):
            return "heading", None, text
    return "text", None, text


def _match_number(text: str) -> tuple[str, str] | None:
    """Return (number, rest) if the line starts with clause numbering."""
    match = _NUMBERED_RE.match(text)
    if not match:
        return None
    rest = (match.group("rest") or "").strip()
    if rest and not (rest[0].isupper() or rest[0] in "\"'("):
        return None  # "2.5 million users", "Section 4 of this Agreement"
    number = next(g for g in match.group("kw", "dec", "top", "roman") if g)
    return number, rest


def _is_heading(text: str, next_text: str) -> bool:
    if len(text) > _MAX_HEADING_CHARS or text.endswith(_HEADING_END_PUNCT):
        return False
    words = text.split()
    if len(words) > _MAX_HEADING_WORDS:
        return False
    first_alpha = next((c for c in text if c.isalpha()), None)
    if first_alpha is None or not first_alpha.isupper():
        return False
    if next_text and next_text[0].islower():
        return False  # sentence wraps onto the next line
    return not next_text or _match_number(next_text) is not None or _is_title_or_caps(words)


def _is_title_or_caps(words: list[str]) -> bool:
    letters = [c for w in words for c in w if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return True
    significant = [w for w in words if w[0].isalpha() and len(w) > 3] or words
    return all(w[0].isupper() for w in significant if w[0].isalpha())


def _is_within(number: str | None, parent: str) -> bool:
    return number is not None and (number == parent or number.startswith(parent + "."))
