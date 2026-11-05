"""Keyword fallback checker, driven by each rule's `check_hints`.

Used when no API key is set, when the AI checker fails, or when the free tier
asks for it. It works like the v1 risk baseline (`legallens/risk.py`): sentence-
bounded regexes over one clause at a time. It can tell that a clause *mentions*
a topic, not whether the wording is lawful, so:

* a match on a `required` rule counts as `compliant` (the topic is covered), and
* a match on a `prohibited` rule is only `unclear` ("possible issue, check it"),
  never `non_compliant`.

Reports built from it are marked partial.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from legallens.compliance.models import ClauseFinding
from legallens.compliance.rulebook import Rule


def match_rule(rule: Rule, text: str) -> re.Match | None:
    """The first hint match of `rule` in `text`, or None if the rule's hints don't fire."""
    hints = rule.check_hints
    if hints is None:
        return None
    if any(p.search(text) for p in hints.compiled("unless")):
        return None
    if hints.with_ and not any(p.search(text) for p in hints.compiled("with_")):
        return None
    matches = []
    for group in hints.compiled("patterns"):
        found = [p.search(text) for p in group]
        if all(found):
            matches.append(found[0])  # the group's first regex marks the evidence
    return min(matches, key=lambda m: m.start()) if matches else None


class KeywordChecker:
    source = "keyword"

    def check(self, clause_texts: Sequence[str], rules: Sequence[Rule]) -> list[ClauseFinding]:
        findings = []
        for index, text in enumerate(clause_texts):
            for rule in rules:
                match = match_rule(rule, text)
                if match is None:
                    continue
                findings.append(self._finding(index, rule, match.group().strip()))
        return findings

    @staticmethod
    def _finding(index: int, rule: Rule, quote: str) -> ClauseFinding:
        if rule.type == "required":
            return ClauseFinding(
                index, rule.id, "compliant", quote,
                f"This clause appears to cover: {rule.title.lower()}. Keyword match only; "
                "the wording was not reviewed.",
            )
        return ClauseFinding(
            index, rule.id, "unclear", quote,
            f"Possible issue: this wording resembles \"{rule.title}\". Keyword match only; "
            "read the clause to confirm.",
        )
