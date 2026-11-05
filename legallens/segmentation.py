"""Rule-based clause segmentation baseline (paper Sec. V-B).

Splits normalized agreement text into clauses using document structure only:

* numbered lines ("1.", "2.1", "3)", "IV.", "Section 4", "Article 2.3", "§ 5")
  start a new clause;
* headings, numbered ("2. Fees") or not ("PRIVACY", "Payment Terms"), close
  the current clause and become the heading of the clauses that follow;
* run-in labels at the start of a paragraph ("Default: We may...",
  "Use of the Card. You may...") start a clause headed by the label;
* in unnumbered text, each paragraph is a clause. Paragraphs end at a blank
  line or, in PDF text without blank lines, at a short line ending a sentence;
* sub-items such as "(a)", "(ii)" and bullets stay inside their parent clause.

A numbered line or heading is only accepted at a plausible boundary (start of
text, after a blank line, after a heading, or after a line ending a sentence),
which stops wrapped lines like "...within\\n30. days" being split. A blank line
after an unfinished sentence is treated as a page break, not a paragraph end.
Line lengths are measured per document so that a wrapped line that fills the
page width is not mistaken for a heading.

Known limitations, kept as baseline behaviour for error analysis:
* sentence-case headings directly followed by text ("Payment terms\\nYou...")
  are kept as clause text unless a blank line or numbered line follows;
* a paragraph whose last line happens to fill the page width merges with the
  next paragraph in PDF text without blank lines;
* numbered lists inside a clause ("1) The Customer...") are split out;
* short standalone lines like "Last updated: 1 March 2026", or a document
  title, are taken as headings and carried by every clause until the next one;
* when a PDF font drops section numbers (extracted as control characters),
  headings are recovered but the numbers are lost.
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
# "Default: We may...", "Use of the Card. You may..."; label checked separately.
_RUN_IN_RE = re.compile(
    r"^(?P<label>[A-Z][A-Za-z0-9'&/,\-\u2013 ]{2,48}?)(?P<sep>[:.])(?:\s+(?=[A-Z(\"'$0-9])|$)"
)
_SUBITEM_RE = re.compile(r"^(?:\(?(?:[a-z]|[ivx]+)\)|(?:[a-z]|[ivx]+)\.|[\u2022\u00b7*\-])\s")
_BULLET_RE = re.compile(r"^[\u2022\u00b7*\-]\s")
_ENDS_SENTENCE_RE = re.compile(r"[.;:!?][\"')\]]*$")
_ENDS_PARAGRAPH_RE = re.compile(r"[.!?][\"')\]]*$")
_HEADING_END_PUNCT = (".", ",", ";", ":", "!", "?")
_MAX_HEADING_CHARS = 80
_MAX_HEADING_WORDS = 10
_MAX_RUN_IN_WORDS = 8
# Pasted web text often has one paragraph per line and no blank lines; PDF
# extraction wraps lines at ~60-100 chars. Longer median lines mean the former.
_PARAGRAPH_LINE_MIN_MEDIAN = 120
# Relative to the document's typical full line: a line at least this long ran
# into the margin and wraps; a sentence-final line shorter than the second
# ratio ended its paragraph early.
_FULL_LINE_RATIO = 0.8
_SHORT_LINE_RATIO = 0.85


@dataclass
class _Line:
    start: int
    end: int
    text: str


@dataclass
class _Layout:
    wrap: float | None  # typical full-line length (90th percentile)
    caps_wrap: float | None  # the same for ALL-CAPS lines, which wrap sooner

    @classmethod
    def measure(cls, lines: list[_Line]) -> _Layout:
        lengths = [len(line.text) for line in lines if line.text]
        caps = [len(line.text) for line in lines if line.text and _is_caps(line.text)]
        return cls(_p90(lengths), _p90(caps))

    def fills_line(self, text: str, next_text: str) -> bool:
        """True if `text` runs to the margin and continues on the next line."""
        if not next_text or _match_number(next_text):
            return False
        width = self.caps_wrap if _is_caps(text) and _is_caps(next_text) and self.caps_wrap else self.wrap
        return width is not None and len(text) >= _FULL_LINE_RATIO * width

    def ends_paragraph(self, text: str) -> bool:
        """True if `text` ends a sentence well before the margin."""
        return (
            self.wrap is not None
            and len(text) < _SHORT_LINE_RATIO * self.wrap
            and bool(_ENDS_PARAGRAPH_RE.search(text))
        )


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
    layout = _Layout.measure(lines)
    paragraph_per_line = _line_breaks_are_paragraphs(lines)

    clauses: list[Clause] = []
    draft: _Draft | None = None
    ctx_number: str | None = None
    ctx_heading: str | None = None
    prev_kind: str | None = None
    prev_text = ""
    after_blank = True  # any blank line since the previous text line
    hard_break = True  # a blank line that is a paragraph break, not a page break
    # Plain headings seen since the last body line. A heading that heads nothing (another
    # heading follows, or the text ends) is really a short body line: a name, an address,
    # an email in a contact block. Those lines are kept as a clause instead of being lost.
    pending: list[_Line] = []
    pending_heading: str | None = None  # the heading in force before the run

    def close() -> None:
        nonlocal draft
        if draft is not None and draft.parts:
            body = "".join(draft.parts).strip()
            clauses.append(
                Clause(len(clauses), body, draft.number, draft.heading, draft.start, draft.end)
            )
        draft = None

    def flush_orphans(keep_last: bool) -> None:
        # Before the first clause a run is a title block ("Terms", "Last updated: ..."),
        # which stays as headings.
        orphans = pending[:-1] if keep_last else pending[:]
        if orphans and clauses:
            body = "\n".join(line.text for line in orphans)
            clauses.append(Clause(len(clauses), body, None, pending_heading, orphans[0].start, orphans[-1].end))
        pending.clear()

    for i, line in enumerate(lines):
        if not line.text:
            after_blank = True
            # A list keeps its intro ("...you will not:") across a blank line.
            if prev_kind not in ("text", "numbered", "run_in") or _ENDS_PARAGRAPH_RE.search(prev_text):
                hard_break = True
            continue

        prev_is_body = prev_kind in ("text", "numbered", "run_in")
        # "dollars) and..." after "...other than U.S." continues the sentence,
        # whatever the line before looked like; "a) Claims..." does not.
        continues_sentence = (
            prev_is_body and line.text[0].islower() and not _SUBITEM_RE.match(line.text)
        )
        starts_paragraph = not continues_sentence and (
            hard_break
            or paragraph_per_line
            or (prev_is_body and layout.ends_paragraph(prev_text))
        )
        at_boundary = not continues_sentence and (
            after_blank
            or starts_paragraph
            or prev_kind in ("heading", "numbered_heading")
            or bool(_ENDS_SENTENCE_RE.search(prev_text))
        )
        next_text = lines[i + 1].text if i + 1 < len(lines) else ""
        following = next((l.text for l in lines[i + 1 :] if l.text), "")
        kind, number, body = _classify(line.text, at_boundary, next_text, following, layout)

        if kind == "heading":
            if not pending:
                pending_heading = ctx_heading
            close()
            pending.append(line)
        else:
            flush_orphans(keep_last=True)

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
        elif kind == "run_in":
            close()
            draft = _Draft(None, number, line.start, line.end)  # number holds the label
            draft.add(line, body, new_paragraph=False)
        else:
            # Bullets belong to the clause that introduces them, even when each
            # bullet looks like its own paragraph.
            new_clause = starts_paragraph and not _BULLET_RE.match(body)
            if draft is None or (draft.number is None and new_clause):
                close()
                # Body directly under "2. Fees" (or "Section 4" + title) is clause 2.
                number = ctx_number if prev_kind in ("heading", "numbered_heading") else None
                draft = _Draft(number, ctx_heading, line.start, line.end)
            draft.add(line, body, new_paragraph=starts_paragraph or bool(_SUBITEM_RE.match(body)))

        prev_kind, prev_text = kind, line.text
        after_blank = hard_break = False

    close()
    flush_orphans(keep_last=False)
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


def _p90(values: list[int]) -> float | None:
    if len(values) < 5:
        return None
    return statistics.quantiles(values, n=10, method="inclusive")[-1]


def _classify(
    text: str, at_boundary: bool, next_text: str, following: str, layout: _Layout
) -> tuple[str, str | None, str]:
    """Return (kind, number or run-in label, body) for a non-blank line.

    `next_text` is the next line ("" if blank or end); `following` is the next
    non-blank line, which may sit across a page break.
    """
    if not at_boundary:
        return "text", None, text
    numbered = _match_number(text)
    if numbered:
        number, rest = numbered
        if not rest or (
            _is_heading(rest, next_text, following) and not layout.fills_line(text, following)
        ):
            return "numbered_heading", number, rest
        return "numbered", number, rest
    if _is_heading(text, next_text, following) and not layout.fills_line(text, following):
        return "heading", None, text
    label = _match_run_in(text)
    if label:
        return "run_in", label, text
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


def _match_run_in(text: str) -> str | None:
    match = _RUN_IN_RE.match(text)
    if not match:
        return None
    label = match.group("label").strip()
    words = label.split()
    if match.group("sep") == ".":
        # "Agreed. We..." is a short sentence, and "ANY KIND. WITHOUT..." is
        # all-caps body text, not a label.
        if len(words) < 2 or _is_caps(text):
            return None
    if len(words) > _MAX_RUN_IN_WORDS or not _is_title_or_caps(words):
        return None
    return label


def _is_heading(text: str, next_text: str, following: str) -> bool:
    if len(text) > _MAX_HEADING_CHARS or text.endswith(_HEADING_END_PUNCT):
        return False
    words = text.split()
    if len(words) > _MAX_HEADING_WORDS:
        return False
    first_alpha = next((c for c in text if c.isalpha()), None)
    if first_alpha is None or not first_alpha.isupper():
        return False
    if following and following[0].islower():
        return False  # sentence wraps onto the next line, possibly across a page break
    return not next_text or _match_number(next_text) is not None or _is_title_or_caps(words)


def _is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _is_title_or_caps(words: list[str]) -> bool:
    if _is_caps(" ".join(words)):
        return True
    significant = [w for w in words if w[0].isalpha() and len(w) > 3] or words
    return all(w[0].isupper() for w in significant if w[0].isalpha())


def _is_within(number: str | None, parent: str) -> bool:
    return number is not None and (number == parent or number.startswith(parent + "."))
