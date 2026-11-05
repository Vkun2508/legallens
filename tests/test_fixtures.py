"""Keyword-mode audits of the fixture policies must find every planted violation and omission."""

import pytest

from legallens.compliance.audit import audit
from legallens.compliance.evaluation import evaluate, load_fixtures

FIXTURES = load_fixtures()


def test_all_four_fixtures_are_present():
    assert {f.name for f in FIXTURES} == {
        "compliant_app_policy", "planted_violations", "planted_omissions", "marketplace_terms",
    }


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_keyword_audit_matches_the_planted_answers(fixture):
    report = audit(fixture.text, fixture.clauses, business_type=fixture.business_type, mode="keyword")
    assert report.mode == "partial"
    violations, missing = evaluate(report, fixture)
    assert violations.fn == set(), "planted violations not found"
    assert violations.fp == set(), "violations flagged that were not planted"
    assert missing.fn == set(), "omissions not detected"
    assert missing.fp == set(), "present clauses reported missing"


def test_compliant_policy_scores_full_marks_but_is_marked_estimated():
    fixture = next(f for f in FIXTURES if f.name == "compliant_app_policy")
    report = audit(fixture.text, fixture.clauses, mode="keyword")
    assert report.score["value"] == 100 and report.score["estimated"] is True
    assert report.missing == []


def test_planted_violations_policy_scores_low():
    fixture = next(f for f in FIXTURES if f.name == "planted_violations")
    report = audit(fixture.text, fixture.clauses, mode="keyword")
    # Keyword mode can only call the planted violations "unclear" (half credit), so the score is
    # well below the compliant policy's but not as low as an AI audit that confirms them.
    assert report.score["value"] <= 60
    assert report.counts["critical"] == 1  # parental consent; unclear rules are not counted as failed
    assert report.status_counts["unclear"] == 8  # the eight planted prohibited rules
