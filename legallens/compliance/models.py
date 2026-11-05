"""The shared finding type both checkers produce."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Verdict = Literal["compliant", "non_compliant", "unclear"]
VERDICTS: tuple[str, ...] = ("compliant", "non_compliant", "unclear")


@dataclass(frozen=True)
class ClauseFinding:
    """One checker's judgement of one clause against one rule.

    `quote` is the words in the clause the judgement rests on; the report finds
    them in the document to get offsets, so a checker never supplies offsets.
    """

    clause_index: int
    rule_id: str
    verdict: Verdict
    quote: str
    explanation: str
    suggested_rewrite: str | None = None
    source: Literal["ai", "keyword"] = "keyword"

    def to_dict(self) -> dict:
        return asdict(self)
