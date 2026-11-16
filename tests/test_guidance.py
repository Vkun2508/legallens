from datetime import date

import pytest
import yaml

from legallens.compliance.guidance import (
    GOALS,
    QUICK_LIMIT,
    QUICK_WATCH_LIMIT,
    build_guidance,
    default_guidance,
    load_guidance,
)
from legallens.compliance.report import AuditReport
from legallens.compliance.rulebook import RULEBOOK_DIR, default_rulebook

RULEBOOK = default_rulebook()
BEFORE = date(2026, 11, 17)  # DPDP not yet in force
AFTER = date(2027, 6, 1)  # DPDP in force


def _report(overrides=None, business_type="app", findings=None):
    """A report where every checkable rule passes, except those in `overrides` (rule id -> status)."""
    report = AuditReport(RULEBOOK, business_type, "partial", None, None, {}, findings or [])
    report.statuses = {r.id: "pass" for r in report.checkable}
    report.statuses.update(overrides or {})
    return report


def _keys(plan):
    return {g["key"]: [i["rule_id"] for i in g["items"]] for g in plan["groups"]}


def _write_variant(tmp_path, change):
    data = yaml.safe_load((RULEBOOK_DIR / "guidance.yaml").read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "guidance.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_default_guidance_covers_every_rule_once():
    guidance = default_guidance()
    placed = [r for t in guidance.topics for r in t.rules]
    assert sorted(placed) == sorted(r.id for r in RULEBOOK.rules)  # includes ui-scope rules


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d["topics"][1]["rules"].append(d["topics"][0]["rules"][0]), "more than one topic"),
        (lambda d: d["topics"][0]["rules"].append("dpdp.no.such_rule"), "doesn't have"),
        (lambda d: d["topics"][0]["rules"].pop(), "no topic"),
        (lambda d: d["goals"].reverse(), "goals must be"),
        (lambda d: d["goals"][1]["groups"].reverse(), "groups must be"),
        (lambda d: d["actions"].pop("check"), "actions"),
        (lambda d: d["topics"].append(dict(d["topics"][0], rules=[])), "rules"),
        (lambda d: d["topics"].append(dict(d["topics"][0], rules=["dpdp.no.such_rule"])), "duplicate topic keys"),
    ],
)
def test_loader_rejects_bad_files(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        load_guidance(_write_variant(tmp_path, change), RULEBOOK)


def test_live_before_dpdp_starts_puts_dpdp_in_before_in_force():
    plan = build_guidance(
        _report({"dpdp.consent.invalid": "missing", "dpdp.notice.language": "missing"}), "live", today=BEFORE
    )
    assert _keys(plan) == {"before_in_force": ["dpdp.consent.invalid", "dpdp.notice.language"]}
    assert plan["groups"][0]["label"] == "Before 13 May 2027"


def test_live_ecommerce_rule_already_in_force_goes_to_now():
    plan = build_guidance(_report({"ecom.grievance_officer": "missing"}, "ecommerce"), "live", today=BEFORE)
    assert _keys(plan) == {"now": ["ecom.grievance_officer"]}


def test_live_after_dpdp_starts():
    report = _report({"dpdp.consent.invalid": "missing", "dpdp.notice.language": "missing"})
    plan = build_guidance(report, "live", today=AFTER)
    assert _keys(plan) == {"now": ["dpdp.consent.invalid"], "next_update": ["dpdp.notice.language"]}
    assert "before_in_force" not in _keys(plan)


def test_prelaunch_splits_minor_from_the_rest():
    report = _report({"dpdp.consent.invalid": "missing", "dpdp.rights.access": "fail", "dpdp.rights.nomination": "missing"})
    plan = build_guidance(report, "prelaunch", today=BEFORE)
    assert _keys(plan) == {
        "before_launch": ["dpdp.consent.invalid", "dpdp.rights.access"],
        "after_launch": ["dpdp.rights.nomination"],
    }


def test_prelaunch_manage_lists_topics_the_business_type_is_subject_to():
    app = build_guidance(_report({"dpdp.consent.invalid": "missing"}), "prelaunch")
    store = build_guidance(_report({"dpdp.consent.invalid": "missing"}, "ecommerce"), "prelaunch")
    app_topics = [m["topic"] for m in app["manage"]]
    assert app_topics[0] == "consent" and "store_terms" not in app_topics and "notice" in app_topics
    assert "store_terms" in [m["topic"] for m in store["manage"]]
    assert len(app_topics) == len(set(app_topics))


def test_quick_keeps_the_top_five_and_trims_the_rest():
    report = _report({r.id: "missing" for r in RULEBOOK.checkable("app")})
    total = len(RULEBOOK.checkable("app"))
    plan = build_guidance(report, "quick")
    assert [len(g["items"]) for g in plan["groups"]] == [QUICK_LIMIT]
    assert plan["total"] == total and plan["more"] == total - QUICK_LIMIT
    assert 0 < len(plan["watch_out"]) <= QUICK_WATCH_LIMIT
    assert all(len(w["points"]) == 1 for w in plan["watch_out"])
    assert plan["manage"] == [] and plan["steps"] == []
    # watch-outs come only from topics of the shown items
    shown = {i["topic"] for i in plan["groups"][0]["items"]}
    assert {w["topic"] for w in plan["watch_out"]} <= shown


def test_items_sort_by_severity_then_status():
    report = _report({
        "dpdp.rights.nomination": "missing",  # minor
        "dpdp.rights.access": "unclear",  # major
        "dpdp.notice.withdrawal_means": "fail",  # major
        "dpdp.notice.board_complaint": "missing",  # major
        "dpdp.consent.invalid": "unclear",  # critical
    })
    plan = build_guidance(report, "prelaunch")
    ids = [i["rule_id"] for g in plan["groups"] for i in g["items"]]
    assert ids == [
        "dpdp.consent.invalid",
        "dpdp.notice.board_complaint",
        "dpdp.notice.withdrawal_means",
        "dpdp.rights.access",
        "dpdp.rights.nomination",
    ]


def test_items_carry_action_topic_and_clause_indexes_from_findings():
    findings = [
        {"rule_id": "dpdp.consent.withdrawal_ease", "verdict": "non_compliant", "clause_index": 4},
        {"rule_id": "dpdp.consent.withdrawal_ease", "verdict": "unclear", "clause_index": 2},
        {"rule_id": "dpdp.consent.withdrawal_ease", "verdict": "non_compliant", "clause_index": 4},
        {"rule_id": "dpdp.consent.withdrawal_ease", "verdict": "compliant", "clause_index": 9},
    ]
    plan = build_guidance(_report({"dpdp.consent.withdrawal_ease": "fail"}, findings=findings), "live", today=AFTER)
    item = plan["groups"][0]["items"][0]
    assert item["clause_indexes"] == [2, 4]
    assert (item["action"], item["action_label"], item["topic"]) == ("reword", "Reword", "consent")
    assert item["severity"] == "critical" and item["status"] == "fail"
    assert [w["topic"] for w in plan["watch_out"]] == ["consent"]


def test_unknown_goal_raises():
    with pytest.raises(ValueError, match="goal"):
        build_guidance(_report(), "nope")


@pytest.mark.parametrize("goal", GOALS)
def test_all_pass_report_has_no_actions(goal):
    plan = build_guidance(_report(), goal, today=BEFORE)
    assert plan["groups"] == [] and plan["total"] == 0 and plan["more"] == 0
    if goal == "live":
        assert plan["manage"] == [] and plan["watch_out"] == []


def test_topics_follow_the_order_the_plan_shows():
    report = _report({"ecom.grievance_officer": "missing", "dpdp.children.parental_consent": "missing"}, "ecommerce")
    plan = build_guidance(report, "live", today=date(2026, 11, 17))
    assert [g["key"] for g in plan["groups"]] == ["now", "before_in_force"]
    assert [m["topic"] for m in plan["manage"]] == ["store_terms", "children"]
    assert [w["topic"] for w in plan["watch_out"]] == ["store_terms", "children"]
