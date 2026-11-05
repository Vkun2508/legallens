from legallens import segment
from legallens.compliance.audit import audit
from legallens.compliance.models import ClauseFinding
from legallens.compliance.report import build_report
from legallens.compliance.rulebook import default_rulebook
from webapp.audit_view import build_view, citation, clause_ref, status_sentences

RULEBOOK = default_rulebook()
TEXT = (
    "1. To withdraw consent, send a signed\nletter by post to our office.\n\n"
    "2. We collect your name and email to create your account.\n\n"
    "3. We sell shoes.\n"
)
CLAUSES = segment(TEXT)


def _view(findings, **kwargs):
    return build_view(TEXT, CLAUSES, build_report(TEXT, CLAUSES, findings, rulebook=RULEBOOK, **kwargs))


def test_citations_read_like_the_law():
    assert citation({"law_name": "DPDP Act", "section": "s.6(4)"}) == "DPDP Act s.6(4)"
    assert citation({"law_name": "E-Commerce Rules", "section": "r.4(4)"}) == "E-Commerce Rules r.4(4)"
    assert citation({"law_name": "Dark Patterns Guidelines", "section": "Annex 1, item 5"}) == (
        "Dark Patterns Guidelines, Annex 1, item 5"
    )
    assert [clause_ref(c) for c in CLAUSES] == ["§ 1", "§ 2", "§ 3"]


def test_clause_takes_its_worst_issue_and_marks_evidence_across_line_breaks():
    view = _view([
        ClauseFinding(0, "dpdp.consent.withdrawal_ease", "unclear", "send a signed letter by post", "x"),
        ClauseFinding(0, "dpdp.notice.withdrawal_means", "unclear", "To withdraw consent", "x"),
        ClauseFinding(1, "dpdp.notice.data_and_purpose", "compliant", "We collect your name", "x"),
    ])
    rows = [r for r in view["rows"] if r["kind"] == "clause"]
    assert [r["tier"] for r in rows] == ["high", "none", "none"]
    first = rows[0]
    assert [i["severity"] for i in first["issues"]] == ["critical", "major"]  # most severe first
    hits = [s for s in first["segments"] if s["hit"]]
    assert [s["text"] for s in hits] == ["To withdraw consent", "send a signed\nletter by post"]
    assert "".join(s["text"] for s in first["segments"]) == TEXT[CLAUSES[0].start : CLAUSES[0].end]
    assert first["note"].startswith("Withdrawing consent must be as easy as giving it (DPDP Act s.6(4))")
    # Keyword findings show what the rule means rather than their generic explanation.
    assert first["issues"][0]["detail"].startswith("If people gave consent with a tap")
    assert [c["rule_id"] for c in rows[1]["covers"]] == ["dpdp.notice.data_and_purpose"]


def test_overlapping_evidence_keeps_one_mark():
    view = _view([
        ClauseFinding(0, "dpdp.consent.withdrawal_ease", "unclear", "send a signed letter by post", "x"),
        ClauseFinding(0, "dpdp.consent.invalid", "unclear", "signed letter", "x"),
    ])
    hits = [s["text"] for s in view["rows"][0]["segments"] if s["hit"]]
    assert hits == ["send a signed\nletter by post"]


def test_status_sentences_count_and_pluralise():
    data = {
        "status_counts": {"pass": 1, "fail": 0, "unclear": 1, "missing": 1},
        "counts": {"critical": 1, "major": 0, "minor": 0},
    }
    assert status_sentences(data, issue_count=1, flagged_clauses=1) == [
        "1 of 3 rules met.",
        "1 required clause is missing and 1 possible issue to check in 1 clause.",
        "Missing or not met by severity: 1 critical.",
    ]
    data = {"status_counts": {"pass": 4, "fail": 0, "unclear": 0, "missing": 0},
            "counts": {"critical": 0, "major": 0, "minor": 0}}
    assert status_sentences(data, 0, 0) == ["4 of 4 rules met.", "No possible issues were found."]


def test_view_of_a_real_audit_has_every_section():
    report = audit(TEXT, CLAUSES, mode="keyword")
    view = build_view(TEXT, CLAUSES, report)
    assert view["clause_count"] == 3
    assert len(view["manual_checks"]) == 8
    assert all(m["citation"] and m["how_to_fix"] for m in view["missing"])
    assert [t for t, _ in view["print_groups"]] == ["high", "medium", "low"]
