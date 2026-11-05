import pytest

from legallens import segment
from legallens.compliance.models import ClauseFinding
from legallens.compliance.report import build_report, locate, rule_status, score
from legallens.compliance.rulebook import default_rulebook

RULEBOOK = default_rulebook()
TEXT = (
    "1. To withdraw consent, send a signed\nletter by post to our office.\n\n"
    "2. You may nominate another person to exercise your rights.\n"
)
CLAUSES = segment(TEXT)


def _report(findings, **kwargs):
    return build_report(TEXT, CLAUSES, findings, rulebook=RULEBOOK, **kwargs)


def test_locate_ignores_line_breaks_and_case():
    start, end = locate("send a signed letter by post", TEXT)
    assert TEXT[start:end] == "send a signed\nletter by post"
    assert locate("not in the text", TEXT) is None
    assert locate("send a signed letter", TEXT, start=CLAUSES[1].start) is None  # outside the window


@pytest.mark.parametrize(
    "rule_type, verdicts, status",
    [
        ("required", set(), "missing"),
        ("required", {"compliant"}, "pass"),
        ("required", {"unclear"}, "unclear"),
        ("required", {"compliant", "non_compliant"}, "fail"),
        ("prohibited", set(), "pass"),
        ("prohibited", {"unclear"}, "unclear"),
        ("prohibited", {"compliant", "non_compliant"}, "fail"),
    ],
)
def test_rule_status(rule_type, verdicts, status):
    rule = next(r for r in RULEBOOK.rules if r.type == rule_type)
    assert rule_status(rule, verdicts) == status


def test_score_weights_by_severity_with_half_credit_for_unclear():
    rules = [RULEBOOK.by_id[i] for i in ("dpdp.consent.withdrawal_ease", "dpdp.rights.access", "dpdp.rights.nomination")]
    # critical 10 (unclear: 5) + major 5 (pass: 5) + minor 2 (missing: 0) = 10 of 17
    statuses = {"dpdp.consent.withdrawal_ease": "unclear", "dpdp.rights.access": "pass", "dpdp.rights.nomination": "missing"}
    assert score(statuses, rules, RULEBOOK.weights) == (round(100 * 10 / 17), 10.0, 17)


def test_empty_document_gets_credit_only_for_prohibited_rules():
    report = _report([], mode="partial")
    checkable = RULEBOOK.checkable("app")
    w = RULEBOOK.weights
    expected = sum(w[r.severity] for r in checkable if r.type == "prohibited") / sum(w[r.severity] for r in checkable)
    assert report.score == {
        "value": round(100 * expected),
        "earned": sum(w[r.severity] for r in checkable if r.type == "prohibited"),
        "possible": sum(w[r.severity] for r in checkable),
        "estimated": True,
    }
    assert {m["rule_id"] for m in report.missing} == {r.id for r in checkable if r.type == "required"}
    # Missing clauses come most severe first.
    severities = [m["severity"] for m in report.missing]
    assert severities == sorted(severities, key=["critical", "major", "minor"].index)


def test_findings_drive_statuses_counts_and_evidence():
    findings = [
        ClauseFinding(0, "dpdp.consent.withdrawal_ease", "non_compliant", "send a signed letter by post",
                      "Withdrawal needs a posted letter.", "Withdraw from Settings.", "ai"),
        ClauseFinding(1, "dpdp.rights.nomination", "compliant", "nominate another person", "Covered.", None, "ai"),
    ]
    report = _report(findings)
    assert report.statuses["dpdp.consent.withdrawal_ease"] == "fail"
    assert report.statuses["dpdp.rights.nomination"] == "pass"
    assert "dpdp.rights.nomination" not in {m["rule_id"] for m in report.missing}

    failed = report.findings[0]
    assert failed["id"] == "f1" and failed["verdict"] == "non_compliant"
    assert TEXT[failed["evidence"]["start"]:failed["evidence"]["end"]] == "send a signed\nletter by post"
    assert failed["suggested_rewrite"] == "Withdraw from Settings."

    counts = report.counts
    assert counts["critical"] == 1 + sum(
        r.type == "required" and r.severity == "critical" for r in RULEBOOK.checkable("app")
    )
    rule_row = next(r for r in report.rules if r["rule_id"] == "dpdp.consent.withdrawal_ease")
    assert rule_row["status"] == "fail" and rule_row["finding_ids"] == ["f1"]
    assert rule_row["verified"] is True and rule_row["source_url"].startswith("https://")


def test_unlocatable_quote_keeps_the_finding_without_evidence():
    report = _report([ClauseFinding(1, "dpdp.rights.nomination", "compliant", "words that are not there", "x")])
    assert report.findings[0]["evidence"] is None
    assert report.statuses["dpdp.rights.nomination"] == "pass"


def test_unknown_rules_out_of_range_clauses_and_duplicates_are_dropped():
    findings = [
        ClauseFinding(0, "dpdp.made.up", "non_compliant", "x", "x"),
        ClauseFinding(9, "dpdp.rights.nomination", "compliant", "x", "x"),
        ClauseFinding(0, "ecom.grievance_officer", "compliant", "x", "x"),  # not applicable to an app
        ClauseFinding(1, "dpdp.rights.nomination", "compliant", "nominate", "x"),
        ClauseFinding(1, "dpdp.rights.nomination", "non_compliant", "nominate", "x"),
    ]
    report = _report(findings)
    assert [(f["clause_index"], f["rule_id"], f["verdict"]) for f in report.findings] == [
        (1, "dpdp.rights.nomination", "compliant"),
    ]


def test_groups_follow_rulebook_order_and_manual_checks_list_ui_patterns():
    data = _report([]).to_dict()
    assert [g["law"] for g in data["groups"]] == ["dpdp", "dark_patterns"]
    first_sections = [s["section"] for s in data["groups"][0]["sections"]]
    assert first_sections[0] == "s.5(1)(i)"
    assert len(data["manual_checks"]) == 8
    assert data["rulebook_version"] == RULEBOOK.version
    assert data["disclaimer"].startswith("LegalLens gives compliance assistance, not legal advice")


def test_ecommerce_audit_includes_ecommerce_rules():
    data = build_report(TEXT, CLAUSES, [], rulebook=RULEBOOK, business_type="ecommerce").to_dict()
    assert [g["law"] for g in data["groups"]] == ["dpdp", "ecommerce", "dark_patterns"]
    assert "ecom.grievance_officer" in {m["rule_id"] for m in data["missing"]}
