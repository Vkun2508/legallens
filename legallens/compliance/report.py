"""Turn clause findings into an audit report: rule statuses, missing clauses, score and groups.

The report logic is shared by both checkers, so AI and keyword audits are scored
the same way. Missing clauses are derived here, not asked of the model: a
`required` rule is missing when no clause has a `compliant` finding for it.

Rule status:
  required:   fail if any clause is non_compliant, else pass if any is compliant,
              else unclear if any is unclear, else missing.
  prohibited: fail if any clause is non_compliant, else unclear if any is unclear,
              else pass.

Score: each checkable rule weighs 10/5/2 by severity (from the rulebook); a pass
earns its full weight, unclear half, fail or missing nothing. Score is the
earned share of the total, 0-100.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from legallens.compliance.models import ClauseFinding
from legallens.compliance.rulebook import SEVERITIES, Rule, Rulebook
from legallens.segmentation import Clause

STATUSES = ("pass", "fail", "unclear", "missing")
_CREDIT = {"pass": 1.0, "unclear": 0.5, "fail": 0.0, "missing": 0.0}


def locate(quote: str, text: str, start: int = 0, end: int | None = None) -> tuple[int, int] | None:
    """Find `quote` in text[start:end], ignoring differences in whitespace and case.

    Checkers quote clause text, whose wrapped lines are joined with spaces; the
    document keeps its line breaks, so whitespace runs are matched loosely.
    """
    words = quote.split()
    if not words:
        return None
    pattern = re.compile(r"\s+".join(re.escape(w) for w in words), re.I)
    match = pattern.search(text, start, len(text) if end is None else end)
    return (match.start(), match.end()) if match else None


def rule_status(rule: Rule, verdicts: set[str]) -> str:
    if "non_compliant" in verdicts:
        return "fail"
    if rule.type == "required":
        if "compliant" in verdicts:
            return "pass"
        return "unclear" if "unclear" in verdicts else "missing"
    return "unclear" if "unclear" in verdicts else "pass"


def score(statuses: dict[str, str], rules: Sequence[Rule], weights: dict[str, int]) -> tuple[int, float, int]:
    """(score 0-100, earned weight, possible weight) over `rules`."""
    possible = sum(weights[r.severity] for r in rules)
    earned = sum(weights[r.severity] * _CREDIT[statuses[r.id]] for r in rules)
    return (round(100 * earned / possible) if possible else 100), earned, possible


@dataclass
class AuditReport:
    rulebook: Rulebook
    business_type: str
    mode: str  # "full" (AI) or "partial" (keyword)
    mode_reason: str | None
    model: str | None
    statuses: dict[str, str]  # rule id -> status, checkable rules only
    findings: list[dict]
    usage: dict = field(default_factory=dict)
    unfair_terms: dict | None = None

    @property
    def checkable(self) -> list[Rule]:
        return self.rulebook.checkable(self.business_type)

    @property
    def score(self) -> dict:
        value, earned, possible = score(self.statuses, self.checkable, self.rulebook.weights)
        return {"value": value, "earned": earned, "possible": possible, "estimated": self.mode != "full"}

    @property
    def counts(self) -> dict:
        """Rules failed or missing, per severity (a rule broken in five clauses counts once)."""
        counts = {s: 0 for s in SEVERITIES}
        for rule in self.checkable:
            if self.statuses[rule.id] in ("fail", "missing"):
                counts[rule.severity] += 1
        return counts

    @property
    def status_counts(self) -> dict:
        return {s: sum(v == s for v in self.statuses.values()) for s in STATUSES}

    def _rule_ref(self, rule: Rule) -> dict:
        law = self.rulebook.law_by_key[rule.law]
        doc = self.rulebook.source_doc(rule)
        return {
            "rule_id": rule.id,
            "law": rule.law,
            "law_name": law.short_name,
            "section": rule.section,
            "also_cites": rule.also_cites,
            "title": rule.title,
            "type": rule.type,
            "severity": rule.severity,
            "basis": rule.basis,
            "verified": rule.source.verified,
            "source_url": doc.url,
            "in_force_from": doc.in_force_from,
        }

    @property
    def rules(self) -> list[dict]:
        by_rule: dict[str, list[str]] = {}
        for f in self.findings:
            by_rule.setdefault(f["rule_id"], []).append(f["id"])
        return [
            {**self._rule_ref(r), "status": self.statuses[r.id], "finding_ids": by_rule.get(r.id, [])}
            for r in self.checkable
        ]

    @property
    def missing(self) -> list[dict]:
        return [
            {**self._rule_ref(r), "what_it_means": r.what_it_means, "how_to_fix": r.how_to_fix,
             "statute_quote": r.source.quote}
            for r in sorted(self.checkable, key=lambda r: SEVERITIES.index(r.severity))
            if self.statuses[r.id] == "missing"
        ]

    @property
    def groups(self) -> list[dict]:
        """Rules grouped by law, then by section, in rulebook order."""
        groups = []
        for law in self.rulebook.laws:
            sections: dict[str, list[str]] = {}
            for rule in self.checkable:
                if rule.law == law.key:
                    sections.setdefault(rule.section, []).append(rule.id)
            if sections:
                groups.append({
                    "law": law.key,
                    "law_name": law.name,
                    "sections": [{"section": s, "rule_ids": ids} for s, ids in sections.items()],
                })
        return groups

    @property
    def manual_checks(self) -> list[dict]:
        return [
            {**self._rule_ref(r), "what_it_means": r.what_it_means, "how_to_fix": r.how_to_fix}
            for r in self.rulebook.applicable(self.business_type)
            if r.scope == "ui"
        ]

    def to_dict(self) -> dict:
        data = {
            "mode": self.mode,
            "mode_reason": self.mode_reason,
            "business_type": self.business_type,
            "rulebook_version": self.rulebook.version,
            "model": self.model,
            "disclaimer": self.rulebook.disclaimer,
            "score": self.score,
            "counts": self.counts,
            "status_counts": self.status_counts,
            "rules": self.rules,
            "findings": self.findings,
            "missing": self.missing,
            "groups": self.groups,
            "manual_checks": self.manual_checks,
            "usage": self.usage,
        }
        if self.unfair_terms is not None:
            data["unfair_terms"] = self.unfair_terms
        return data


def build_report(
    text: str,
    clauses: Sequence[Clause],
    findings: Sequence[ClauseFinding],
    *,
    rulebook: Rulebook,
    business_type: str = "app",
    mode: str = "full",
    mode_reason: str | None = None,
    model: str | None = None,
    usage: dict | None = None,
) -> AuditReport:
    checkable = {r.id: r for r in rulebook.checkable(business_type)}
    verdicts: dict[str, set[str]] = {rule_id: set() for rule_id in checkable}
    rows, seen = [], set()
    for f in sorted(findings, key=lambda f: (f.clause_index, f.rule_id)):
        key = (f.clause_index, f.rule_id)
        if f.rule_id not in checkable or not 0 <= f.clause_index < len(clauses) or key in seen:
            continue  # checkers are validated upstream; this keeps the report consistent regardless
        seen.add(key)
        verdicts[f.rule_id].add(f.verdict)
        rule, clause = checkable[f.rule_id], clauses[f.clause_index]
        span = locate(f.quote, text, clause.start, clause.end)
        rows.append({
            "id": f"f{len(rows) + 1}",
            "rule_id": rule.id,
            "law": rule.law,
            "section": rule.section,
            "title": rule.title,
            "severity": rule.severity,
            "type": rule.type,
            "verdict": f.verdict,
            "clause_index": f.clause_index,
            "evidence": {"start": span[0], "end": span[1], "text": text[span[0]:span[1]]} if span else None,
            "explanation": f.explanation,
            "suggested_rewrite": f.suggested_rewrite,
            "how_to_fix": rule.how_to_fix,
            "source": f.source,
        })
    statuses = {rule_id: rule_status(checkable[rule_id], v) for rule_id, v in verdicts.items()}
    return AuditReport(rulebook, business_type, mode, mode_reason, model, statuses, rows, usage or {})
