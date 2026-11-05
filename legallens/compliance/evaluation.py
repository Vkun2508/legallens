"""Score audit reports against fixture policies with planted violations and omissions.

Each fixture is `<name>.md` plus `<name>.expected.yaml`:

    business_type: app
    scope_laws: [dpdp, dark_patterns]     # optional; defaults to every applicable law
    violations:                          # prohibited rules, located by a phrase in the clause
      - {rule_id: dpdp.consent.invalid, clause_contains: "By using the app"}
    missing: [dpdp.rights.nomination]    # required rules the policy must not pass
    uncertain_violations: [...]          # optional: borderline pairs, left out of scoring
    uncertain_missing: [...]             # optional: borderline required rules, left out of scoring

Two measures:
* violations: (rule, clause) pairs flagged on prohibited rules. `strict` counts only
  `non_compliant`; otherwise `unclear` counts too (the keyword checker never says more).
* missing: required rules whose status is anything but `pass`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from legallens.compliance.report import AuditReport
from legallens.preprocess import load_document
from legallens.segmentation import Clause, segment

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "policies"


@dataclass
class Fixture:
    name: str
    text: str
    clauses: list[Clause]
    business_type: str
    scope_laws: list[str] | None
    violations: list[dict]
    missing: list[str]
    uncertain_violations: list[dict] = field(default_factory=list)
    uncertain_missing: list[str] = field(default_factory=list)


def load_fixtures(directory: Path = FIXTURE_DIR) -> list[Fixture]:
    fixtures = []
    for path in sorted(directory.glob("*.md")):
        expected = yaml.safe_load(path.with_suffix(".expected.yaml").read_text(encoding="utf-8"))
        text = load_document(path)
        fixtures.append(Fixture(
            name=path.stem,
            text=text,
            clauses=segment(text),
            business_type=expected.get("business_type", "app"),
            scope_laws=expected.get("scope_laws"),
            violations=expected.get("violations") or [],
            missing=expected.get("missing") or [],
            uncertain_violations=expected.get("uncertain_violations") or [],
            uncertain_missing=expected.get("uncertain_missing") or [],
        ))
    return fixtures


def _clause_index(clauses: list[Clause], phrase: str) -> int:
    for clause in clauses:
        if phrase.lower() in clause.text.lower():
            return clause.index
    raise ValueError(f"no clause contains {phrase!r}")


@dataclass
class Score:
    tp: set = field(default_factory=set)
    fp: set = field(default_factory=set)
    fn: set = field(default_factory=set)

    @property
    def precision(self) -> float:
        return len(self.tp) / (len(self.tp) + len(self.fp)) if self.tp or self.fp else 1.0

    @property
    def recall(self) -> float:
        return len(self.tp) / (len(self.tp) + len(self.fn)) if self.tp or self.fn else 1.0

    def add(self, other: Score, tag: str) -> None:
        self.tp |= {(tag, *k) if isinstance(k, tuple) else (tag, k) for k in other.tp}
        self.fp |= {(tag, *k) if isinstance(k, tuple) else (tag, k) for k in other.fp}
        self.fn |= {(tag, *k) if isinstance(k, tuple) else (tag, k) for k in other.fn}


def _compare(predicted: set, gold: set) -> Score:
    return Score(predicted & gold, predicted - gold, gold - predicted)


def evaluate(report: AuditReport, fixture: Fixture, *, strict: bool = False) -> tuple[Score, Score]:
    """(violation score over (rule_id, clause_index) pairs, missing score over rule ids)."""
    in_scope = {
        r.id: r for r in report.rulebook.checkable(fixture.business_type)
        if fixture.scope_laws is None or r.law in fixture.scope_laws
    }
    flagged = {"non_compliant"} if strict else {"non_compliant", "unclear"}
    predicted_violations = {
        (f["rule_id"], f["clause_index"]) for f in report.findings
        if f["rule_id"] in in_scope and in_scope[f["rule_id"]].type == "prohibited" and f["verdict"] in flagged
    }
    def pairs(items: list[dict]) -> set:
        return {(v["rule_id"], _clause_index(fixture.clauses, v["clause_contains"])) for v in items}

    unsure_pairs, unsure_rules = pairs(fixture.uncertain_violations), set(fixture.uncertain_missing)
    gold_violations = pairs(fixture.violations) - unsure_pairs
    predicted_missing = {
        rule_id for rule_id, rule in in_scope.items()
        if rule.type == "required" and report.statuses[rule_id] != "pass"
    }
    return (
        _compare(predicted_violations - unsure_pairs, gold_violations),
        _compare(predicted_missing - unsure_rules, set(fixture.missing) - unsure_rules),
    )


def per_rule(score: Score) -> dict[str, Counter]:
    """TP/FP/FN counts per rule id (the rule id is the second element of each tagged key)."""
    table: dict[str, Counter] = {}
    for kind in ("tp", "fp", "fn"):
        for key in getattr(score, kind):
            table.setdefault(key[1], Counter())[kind] += 1
    return dict(sorted(table.items()))
