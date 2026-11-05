import shutil

import pytest
import yaml
from pydantic import ValidationError

from legallens.compliance.keyword import KeywordChecker, match_rule
from legallens.compliance.rulebook import RULEBOOK_DIR, default_rulebook, load_rulebook

RULEBOOK = default_rulebook()
TEXT_RULES = [r for r in RULEBOOK.rules if r.scope == "text"]


def test_rulebook_loads_with_version_and_three_laws():
    assert RULEBOOK.version
    assert [law.key for law in RULEBOOK.laws] == ["dpdp", "ecommerce", "dark_patterns"]
    assert len(RULEBOOK.by_id) == len(RULEBOOK.rules)


def test_all_thirteen_dark_patterns_are_listed():
    dark = [r for r in RULEBOOK.rules if r.law == "dark_patterns"]
    assert len(dark) == 13
    assert sum(r.scope == "ui" for r in dark) == 8


def test_every_rule_cites_a_source_with_a_url():
    for rule in RULEBOOK.rules:
        assert rule.source.quote.strip(), rule.id
        assert RULEBOOK.source_doc(rule).url.startswith("https://"), rule.id


def test_statutory_rules_are_verified_against_the_official_text():
    # DPDP and E-Commerce quotes were checked against the Gazette; dark patterns were not yet.
    for rule in RULEBOOK.rules:
        assert rule.source.verified == (rule.law != "dark_patterns"), rule.id


@pytest.mark.parametrize(
    "business_type, laws, has_marketplace_rule",
    [
        ("app", {"dpdp", "dark_patterns"}, False),
        ("ecommerce", {"dpdp", "ecommerce", "dark_patterns"}, False),
        ("marketplace", {"dpdp", "ecommerce", "dark_patterns"}, True),
    ],
)
def test_applicable_rules_depend_on_business_type(business_type, laws, has_marketplace_rule):
    rules = RULEBOOK.applicable(business_type)
    assert {r.law for r in rules} == laws
    assert any(r.id == "ecom.seller_info" for r in rules) == has_marketplace_rule
    assert all(r.scope == "text" for r in RULEBOOK.checkable(business_type))


def test_unknown_business_type_is_rejected():
    with pytest.raises(ValueError):
        RULEBOOK.applicable("bank")


@pytest.fixture
def rulebook_copy(tmp_path):
    target = tmp_path / "rulebook"
    shutil.copytree(RULEBOOK_DIR, target)
    return target


def _edit_first_rule(directory, **changes):
    path = directory / "dpdp.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["rules"][0].update(changes)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "dpdp.consent.invalid"},  # duplicate id
        {"severity": "severe"},
        {"typo_field": "x"},
        {"check_hints": {"patterns": ["(unclosed"]}},
        {"check_hints": {"patterns": [[]]}},  # an empty pattern group
        {"check_hints": {"patterns": [["ok", "(bad"]]}},
        {"examples": None},  # a text rule must have examples
    ],
)
def test_invalid_rulebooks_are_rejected(rulebook_copy, changes):
    _edit_first_rule(rulebook_copy, **changes)
    with pytest.raises((ValidationError, ValueError)):
        load_rulebook(rulebook_copy)


# The per-rule fallback tests: every text rule's own examples.
@pytest.mark.parametrize(
    "rule, text",
    [(r, t) for r in TEXT_RULES for t in r.examples.match],
    ids=lambda v: v.id if hasattr(v, "id") else "",
)
def test_rule_hints_match_their_examples(rule, text):
    assert match_rule(rule, text), f"{rule.id} should match: {text}"


@pytest.mark.parametrize(
    "rule, text",
    [(r, t) for r in TEXT_RULES for t in r.examples.no_match],
    ids=lambda v: v.id if hasattr(v, "id") else "",
)
def test_rule_hints_skip_their_counter_examples(rule, text):
    assert not match_rule(rule, text), f"{rule.id} should not match: {text}"


def test_keyword_verdicts_never_claim_a_violation():
    rules = [RULEBOOK.by_id["dpdp.consent.withdrawal_ease"], RULEBOOK.by_id["dpdp.rights.nomination"]]
    clauses = [
        "To withdraw consent, you must send a signed letter by post.",
        "You may nominate another person to exercise your rights.",
    ]
    findings = KeywordChecker().check(clauses, rules)
    assert [(f.clause_index, f.rule_id, f.verdict) for f in findings] == [
        (0, "dpdp.consent.withdrawal_ease", "unclear"),
        (1, "dpdp.rights.nomination", "compliant"),
    ]
    assert findings[0].quote in clauses[0]
    assert all(f.source == "keyword" for f in findings)


def test_pattern_groups_need_every_part_in_the_clause():
    rule = RULEBOOK.by_id["dpdp.fiduciary.breach_disclaimer"]
    # "At your own risk" alone is a general liability phrase; with security wording it disclaims breaches.
    assert not match_rule(rule, "You use the beta features at your own risk.")
    match = match_rule(rule, "Data sent over the internet is never fully secure. You use the site at your own risk.")
    assert match and match.group() == "at your own risk"


def test_coppa_style_under_13_wording_does_not_satisfy_dpdp_children_rule():
    rule = RULEBOOK.by_id["dpdp.children.parental_consent"]
    assert not match_rule(rule, "We do not knowingly collect data from children under 13 without parental consent.")
