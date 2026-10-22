from pathlib import Path

import pytest

from legallens import load_document, segment
from legallens.risk import CATEGORIES, TIERS, assess

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "samples" / "sample_tos.txt"


def test_sample_agreement_tiers():
    results = [assess(c.text) for c in segment(load_document(SAMPLE))]
    assert [(r.tier, r.categories) for r in results] == [
        ("low", ["consent_by_use"]),
        ("none", []),
        ("high", ["auto_renewal"]),  # "recurring billing" in a definition: a keyword false alarm
        ("high", ["auto_renewal", "fees"]),
        ("high", ["unilateral_change"]),
        ("high", ["data_sharing"]),
        ("medium", ["liability"]),
        ("high", ["arbitration"]),
        ("high", ["unilateral_change"]),
    ]


@pytest.mark.parametrize(
    "text, category",
    [
        ("Any dispute will be resolved by binding individual arbitration.", "arbitration"),
        ("YOU WAIVE ANY RIGHT TO A JURY TRIAL.", "arbitration"),
        ("We reserve the right, at any time, to modify these Terms.", "unilateral_change"),
        ("Your plan renews automatically each month.", "auto_renewal"),
        ("We may sell information about you to partners.", "data_sharing"),
        ("In no event shall we be liable for lost profits.", "liability"),
        ("You agree to indemnify and hold us harmless.", "indemnity"),
        ("A late fee of $25 applies.", "fees"),
        ("We may suspend your account for any reason.", "termination"),
        ("These Terms are governed by the laws of Italy.", "governing_law"),
        ("By using the Service, you agree to these Terms.", "consent_by_use"),
        ("You consent to autodialed calls.", "communications"),
    ],
)
def test_each_category_is_detected(text, category):
    result = assess(text)
    assert result.categories == [category]
    assert result.tier == next(c.tier for c in CATEGORIES if c.key == category)


def test_tier_is_the_most_severe_category():
    result = assess("We may suspend your account. Disputes go to arbitration. A late fee applies.")
    assert result.tier == "high"
    assert result.categories == ["arbitration", "fees", "termination"]


@pytest.mark.parametrize("text", ["The Service is available in English.", ""])
def test_clauses_without_watched_terms_are_not_flagged(text):
    result = assess(text)
    assert result.tier == "none"
    assert result.categories == [] and result.evidence == []


def test_consumer_right_is_not_a_one_sided_change():
    assert "unilateral_change" not in assess("You may cancel at any time.").categories


def test_evidence_offsets_point_into_the_clause_text():
    text = "Fees renew automatically. We may change fees at our sole discretion."
    result = assess(text)
    assert result.evidence
    for e in result.evidence:
        assert text[e.start : e.end] == e.text
    starts = [e.start for e in result.evidence]
    assert starts == sorted(starts)
    assert all(a.end <= b.start for a, b in zip(result.evidence, result.evidence[1:]))


def test_categories_are_ordered_by_tier():
    order = [TIERS.index(c.tier) for c in CATEGORIES]
    assert order == sorted(order)
