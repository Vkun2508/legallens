"""Rule-based risk tagging for clauses: the keyword baseline (paper Sec. V-C, arm 1).

Each category from the LegalLens taxonomy has a tier and a set of phrase
patterns. A clause is tagged with every category whose patterns match, and its
tier is the highest tier among those categories. Every match is kept as
evidence, with offsets into the clause text, so a reader can see why a clause
was flagged.

This is a keyword baseline, not a legal judgement. It misses terms phrased in
ways the patterns don't anticipate, and it flags harmless mentions (a clause
that says "we never sell your data" still mentions selling data). A tier says
which topics a clause touches and how closely it is worth reading, not whether
the clause is unfair or enforceable.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

TIERS = ("high", "medium", "low")
TIER_LABELS = {
    "high": ("High", "Review closely"),
    "medium": ("Medium", "Worth knowing"),
    "low": ("Low", "For awareness"),
    "none": ("No flags", "No watched terms found"),
}


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    tier: str
    description: str
    patterns: tuple[re.Pattern, ...]


def _patterns(*sources: str) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(source, re.I) for source in sources)


# Gaps like [^.]{0,80} keep a match inside one sentence.
CATEGORIES: tuple[Category, ...] = (
    Category(
        "arbitration", "Arbitration and waived rights", "high",
        "Disputes go to private arbitration, or you give up a jury trial or class action.",
        _patterns(
            r"\barbitrat(?:ion|or|ors|e|ed)\b",
            r"\bclass[- ]action\b",
            r"\bjury trials?\b",
            r"\bwaive[sd]?\b[^.]{0,60}?\b(?:rights?|jury|class|claims?)\b",
        ),
    ),
    Category(
        "unilateral_change", "One-sided changes", "high",
        "The company can change the terms, prices or service on its own.",
        _patterns(
            r"\bwe (?:may|can|will)(?: also)? (?:update|change|modify|amend|revise|alter)\b",
            r"\breserves? the right\b[^.]{0,60}?\b(?:change|modify|amend|update|revise|alter)\b",
            r"\b(?:sole|absolute) discretion\b",
            r"\bwithout (?:prior |advance |any )?notice\b",
        ),
    ),
    Category(
        "auto_renewal", "Automatic renewal", "high",
        "You are charged again automatically unless you cancel in time.",
        _patterns(
            r"\bauto(?:matic(?:ally)?)?[- ]?renew\w*\b",
            r"\brenews? automatically\b",
            r"\brecurring (?:charges?|billing|payments?|fees?)\b",
            r"\bfree trials?\b",
        ),
    ),
    Category(
        "data_sharing", "Data sharing", "high",
        "Your personal information can be shared with, or sold to, other companies.",
        _patterns(
            r"\b(?:share|shares|shared|sharing|sell|sells|sold|disclose|discloses|disclosed|transfer|transfers|rent)\b"
            r"[^.]{0,80}?\b(?:personal (?:data|information)|your (?:data|information)|information about you)\b",
            r"\b(?:personal (?:data|information)|your (?:data|information))\b[^.]{0,80}?"
            r"\b(?:shared|sold|disclosed|transferred)\b",
            r"\b(?:advertising|marketing) partners\b",
        ),
    ),
    Category(
        "liability", "Limited liability", "medium",
        "The company limits what it owes you if something goes wrong.",
        _patterns(
            r"\blimitation of liability\b",
            r"\b(?:(?:will|shall) )?not (?:be )?(?:liable|responsible) for\b",
            r"\bin no event\b",
            r"\bas is\b",
            r"\bdisclaims?\b",
            r"\bconsequential (?:damages|loss)\b",
        ),
    ),
    Category(
        "indemnity", "Indemnification", "medium",
        "You may have to cover the company's legal costs or losses.",
        _patterns(r"\bindemnif\w*\b", r"\bhold (?:us |[A-Z]\w+ )?harmless\b"),
    ),
    Category(
        "fees", "Fees and interest", "medium",
        "Charges, penalties or interest rates.",
        _patterns(
            r"\b(?:late|annual|returned payment|cash advance|foreign transaction|research|cancellation|"
            r"early termination|termination|service|processing|renewal|subscription|transaction) fees?\b",
            r"\binterest (?:charges?|rates?)\b",
            r"\bpenalt(?:y|ies)\b",
            r"\bannual percentage rates?\b",
            r"\bwe (?:may|will) charge\b",
        ),
    ),
    Category(
        "termination", "Suspension and termination", "medium",
        "Accounts, access or the agreement can be suspended, closed or cancelled.",
        _patterns(
            r"\b(?:suspend|suspends|suspended|suspension|terminate|terminates|terminated|termination|"
            r"cancel|cancels|cancelled|canceled|cancellation|revoke|revokes|revoked)\b[^.]{0,80}?"
            r"\b(?:account|access|card|subscription|privileges|service|agreement|terms)s?\b",
        ),
    ),
    Category(
        "governing_law", "Governing law and venue", "medium",
        "Which laws apply and where disputes must be heard.",
        _patterns(
            r"\bgoverned by\b[^.]{0,40}?\blaws?\b",
            r"\b(?:exclusive|personal) jurisdiction\b",
            r"\bvenue\b",
        ),
    ),
    Category(
        "consent_by_use", "Agreement by use", "low",
        "Using the service counts as accepting the terms.",
        _patterns(
            r"\bby (?:using|accessing|downloading|installing|creating|signing|continuing)\b[^.]{0,100}?\byou agree\b",
        ),
    ),
    Category(
        "communications", "Calls and messages", "low",
        "Consent to calls, texts or recording.",
        _patterns(
            r"\b(?:autodialed|auto-dialed|prerecorded|pre-recorded|artificial voice)\b",
            r"\btext messages?\b",
            r"\bmonitor and record\b",
        ),
    ),
)
CATEGORY_BY_KEY = {c.key: c for c in CATEGORIES}


@dataclass
class Evidence:
    category: str
    start: int  # offsets into the clause text
    end: int
    text: str


@dataclass
class Assessment:
    tier: str  # "high", "medium", "low" or "none"
    categories: list[str] = field(default_factory=list)  # most severe first
    evidence: list[Evidence] = field(default_factory=list)  # ordered by position

    def to_dict(self) -> dict:
        return asdict(self)


def assess(text: str) -> Assessment:
    """Tag one clause's text with risk categories and a tier."""
    evidence = []
    for category in CATEGORIES:
        for pattern in category.patterns:
            evidence.extend(
                Evidence(category.key, m.start(), m.end(), m.group()) for m in pattern.finditer(text)
            )
    if not evidence:
        return Assessment("none")

    keys = {e.category for e in evidence}
    categories = [c.key for c in CATEGORIES if c.key in keys]  # CATEGORIES is ordered by tier
    tier = min((CATEGORY_BY_KEY[k].tier for k in keys), key=TIERS.index)
    return Assessment(tier, categories, _merge_overlaps(evidence))


def _merge_overlaps(evidence: list[Evidence]) -> list[Evidence]:
    """Keep non-overlapping spans, preferring the earliest and then the longest."""
    kept: list[Evidence] = []
    for e in sorted(evidence, key=lambda e: (e.start, -(e.end - e.start))):
        if kept and e.start < kept[-1].end:
            continue
        kept.append(e)
    return kept
