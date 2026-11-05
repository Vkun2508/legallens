"""Load and validate the compliance rulebook (`legallens/rulebook/*.yaml`).

The rulebook is data, not code: each law file lists rules with a citation, a
plain-language explanation, template wording for a fix, keyword hints for the
fallback checker, and the statutory quote it rests on. Loading validates every
field (unknown keys are errors, so a typo can't silently drop a field) and
compiles the hint regexes once.
"""

from __future__ import annotations

import re
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

RULEBOOK_DIR = Path(__file__).resolve().parent.parent / "rulebook"

Severity = Literal["critical", "major", "minor"]
SEVERITIES: tuple[str, ...] = ("critical", "major", "minor")
BusinessType = Literal["app", "ecommerce", "marketplace"]
BUSINESS_TYPES: tuple[str, ...] = ("app", "ecommerce", "marketplace")

# Which `applies_to` values each business type is subject to.
_APPLIES = {
    "app": {"all"},
    "ecommerce": {"all", "ecommerce"},
    "marketplace": {"all", "ecommerce", "marketplace"},
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CheckHints(_Strict):
    """Regexes for the keyword fallback, matched case-insensitively against one clause.

    A clause matches when any of `patterns` matches, at least one of `with_` also
    matches (if given), and none of `unless` matches. A pattern may be a list of
    regexes that must all match somewhere in the clause, in any order (for
    example "at your own risk" together with a word about security).
    """

    patterns: list[str | list[str]] = Field(min_length=1)
    with_: list[str] = Field(default_factory=list, alias="with")
    unless: list[str] = Field(default_factory=list)

    _compiled: dict = PrivateAttr(default_factory=dict)

    @field_validator("patterns", "with_", "unless")
    @classmethod
    def _valid_regex(cls, sources: list) -> list:
        for source in sources:
            group = [source] if isinstance(source, str) else source
            if not group:
                raise ValueError("a pattern group needs at least one regex")
            for regex in group:
                try:
                    re.compile(regex, re.I)
                except re.error as exc:
                    raise ValueError(f"invalid regex {regex!r}: {exc}") from exc
        return sources

    def model_post_init(self, _context) -> None:
        self._compiled = {
            "patterns": tuple(
                tuple(re.compile(s, re.I) for s in ([p] if isinstance(p, str) else p)) for p in self.patterns
            ),
            "with_": tuple(re.compile(s, re.I) for s in self.with_),
            "unless": tuple(re.compile(s, re.I) for s in self.unless),
        }

    def compiled(self, name: str) -> tuple:
        """`patterns` gives a tuple of groups (tuples of regexes); the others a tuple of regexes."""
        return self._compiled[name]


class Examples(_Strict):
    match: list[str] = Field(min_length=1)
    no_match: list[str] = Field(min_length=1)


class SourceRef(_Strict):
    doc: str
    quote: str
    verified: bool


class SourceDoc(_Strict):
    title: str
    url: str
    in_force_from: str | None = None
    in_force_note: str | None = None


class Rule(_Strict):
    id: str = Field(pattern=r"^[a-z_]+(?:\.[a-z_]+)+$")
    law: str
    section: str
    also_cites: list[str] = Field(default_factory=list)
    title: str
    type: Literal["required", "prohibited"]
    severity: Severity
    basis: Literal["statute", "rules", "best_practice", "guidelines"]
    scope: Literal["text", "ui"] = "text"
    applies_to: Literal["all", "ecommerce", "marketplace"] = "all"
    what_it_means: str
    how_to_fix: str
    check_hints: CheckHints | None = None
    examples: Examples | None = None
    source: SourceRef

    @model_validator(mode="after")
    def _text_rules_are_checkable(self) -> Rule:
        if self.scope == "text" and (self.check_hints is None or self.examples is None):
            raise ValueError(f"{self.id}: text rules need check_hints and examples")
        return self


class Law(_Strict):
    key: str
    name: str
    short_name: str
    summary: str = ""  # one line on what the law's rules cover, for the homepage
    sources: dict[str, SourceDoc]


class Rulebook(_Strict):
    version: str
    updated: str
    weights: dict[Severity, int]
    disclaimer: str
    laws: list[Law]
    rules: list[Rule]

    @model_validator(mode="after")
    def _consistent(self) -> Rulebook:
        ids = [r.id for r in self.rules]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate rule ids: {duplicates}")
        laws = {law.key: law for law in self.laws}
        for rule in self.rules:
            if rule.law not in laws:
                raise ValueError(f"{rule.id}: unknown law {rule.law!r}")
            if rule.source.doc not in laws[rule.law].sources:
                raise ValueError(f"{rule.id}: unknown source doc {rule.source.doc!r}")
        if set(self.weights) != set(SEVERITIES):
            raise ValueError("weights must cover critical, major and minor")
        return self

    @cached_property
    def by_id(self) -> dict[str, Rule]:
        return {r.id: r for r in self.rules}

    @cached_property
    def law_by_key(self) -> dict[str, Law]:
        return {law.key: law for law in self.laws}

    def source_doc(self, rule: Rule) -> SourceDoc:
        return self.law_by_key[rule.law].sources[rule.source.doc]

    def applicable(self, business_type: str = "app") -> list[Rule]:
        """Rules that apply to this kind of business, text and UI scope alike."""
        if business_type not in _APPLIES:
            raise ValueError(f"business_type must be one of {', '.join(BUSINESS_TYPES)}")
        allowed = _APPLIES[business_type]
        return [r for r in self.rules if r.applies_to in allowed]

    def checkable(self, business_type: str = "app") -> list[Rule]:
        """Applicable rules that can be judged from document text (and are scored)."""
        return [r for r in self.applicable(business_type) if r.scope == "text"]


def _read_law(path: Path) -> tuple[Law, list[dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    law = Law(
        key=data["law"], name=data["name"], short_name=data["short_name"],
        summary=data.get("summary", ""), sources=data["sources"],
    )
    default_applies = data.get("applies_to", "all")
    rules = [{"law": law.key, "applies_to": default_applies, **raw} for raw in data["rules"]]
    return law, rules


def load_rulebook(directory: Path | str = RULEBOOK_DIR) -> Rulebook:
    directory = Path(directory)
    manifest = yaml.safe_load((directory / "rulebook.yaml").read_text(encoding="utf-8"))
    laws, rules = [], []
    for name in manifest["laws"]:
        law, law_rules = _read_law(directory / name)
        laws.append(law)
        rules.extend(law_rules)
    return Rulebook(
        version=manifest["version"],
        updated=str(manifest["updated"]),
        weights=manifest["weights"],
        disclaimer=manifest["disclaimer"].strip(),
        laws=laws,
        rules=rules,
    )


@lru_cache(maxsize=1)
def default_rulebook() -> Rulebook:
    return load_rulebook()
