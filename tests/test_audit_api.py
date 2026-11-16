from pathlib import Path

import pytest
from fake_llm import FakeClient, item, reply
from fastapi.testclient import TestClient

from legallens.compliance.llm import LLMChecker
from webapp.main import app, get_llm_checker

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "policies"
client = TestClient(app)


def _audit(**data):
    files = data.pop("files", None)
    return client.post("/api/audit", data=data, files=files)


def test_audit_without_api_key_is_a_partial_keyword_report():
    text = (FIXTURES / "planted_violations.md").read_text(encoding="utf-8")
    response = _audit(text=text)
    assert response.status_code == 200
    result = response.json()
    assert result["source"] == "Pasted text"
    assert (result["mode"], result["mode_reason"], result["model"]) == ("partial", "no_api_key", None)
    assert result["score"]["estimated"] is True and 0 <= result["score"]["value"] <= 100
    assert result["warnings"][0].startswith("This is a keyword check of the wording")
    assert result["rulebook_version"] and result["disclaimer"]
    assert {f["verdict"] for f in result["findings"]} <= {"compliant", "unclear"}
    assert "dpdp.rights.nomination" in {m["rule_id"] for m in result["missing"]}
    assert len(result["manual_checks"]) == 8
    assert len(result["clauses"]) == 14 and "QuickCart" in result["text"]
    # Evidence offsets point into the returned document text.
    for f in result["findings"]:
        if f["evidence"]:
            assert result["text"][f["evidence"]["start"]:f["evidence"]["end"]] == f["evidence"]["text"]


def test_audit_accepts_file_uploads_and_business_type():
    data = (FIXTURES / "marketplace_terms.md").read_bytes()
    response = _audit(files={"file": ("terms.md", data)}, business_type="marketplace")
    assert response.status_code == 200
    result = response.json()
    assert result["source"] == "terms.md" and result["business_type"] == "marketplace"
    assert "ecom.grievance_officer" in {m["rule_id"] for m in result["missing"]}


def test_keyword_mode_can_be_requested():
    response = _audit(text="1. You may nominate another person.", mode="keyword")
    assert response.json()["mode_reason"] == "keyword_requested"


@pytest.mark.parametrize(
    "data, status, detail",
    [
        ({"text": "Some policy.", "business_type": "bank"}, 400, "business_type"),
        ({"text": "Some policy.", "mode": "magic"}, 400, "mode"),
        ({"text": "   "}, 400, "not both or neither"),
        ({"text": "word " * 31_000}, 413, "longer than"),
    ],
)
def test_bad_input_is_rejected(data, status, detail):
    response = _audit(**data)
    assert response.status_code == status
    assert detail in response.json()["detail"]


GOAL_ERROR = "Choose what you need from this review: prelaunch, live or quick."
GUIDANCE_KEYS = {"version", "goal", "label", "intro", "groups", "manage", "watch_out", "steps", "more", "total"}


def test_audit_carries_guidance_for_the_default_goal():
    result = _audit(text=(FIXTURES / "planted_violations.md").read_text(encoding="utf-8")).json()
    assert result["guidance"]["goal"] == "live"


@pytest.mark.parametrize("goal", ["prelaunch", "live", "quick"])
def test_every_goal_returns_a_guidance_plan(goal):
    response = _audit(text="1. You may nominate another person.", goal=goal)
    assert response.status_code == 200
    guidance = response.json()["guidance"]
    assert set(guidance) == GUIDANCE_KEYS and guidance["goal"] == goal


def test_quick_goal_shows_at_most_five_and_counts_the_rest():
    guidance = _audit(text="1. We sell shoes.", goal="quick").json()["guidance"]
    shown = sum(len(g["items"]) for g in guidance["groups"])
    assert shown == 5 and guidance["more"] == guidance["total"] - shown > 0


def test_unknown_goal_is_rejected():
    response = _audit(text="Some policy.", goal="nope")
    assert response.status_code == 400
    assert response.json()["detail"] == GOAL_ERROR


def test_unknown_goal_on_the_html_form_shows_the_message():
    response = client.post("/audit", data={"text": "Some policy.", "goal": "nope"})
    assert response.status_code == 400
    assert GOAL_ERROR in response.text


@pytest.fixture
def fake_ai():
    def answer(kwargs):
        return reply([item(0, "dpdp.consent.withdrawal_ease", "non_compliant", "send a signed letter by post",
                           "Withdrawal is harder than giving consent.", "Withdraw any time from Settings.")])

    checker = LLMChecker(client=FakeClient([answer]), model="claude-opus-5-5", max_usd=1.0)
    app.dependency_overrides[get_llm_checker] = lambda: checker
    yield
    app.dependency_overrides.clear()


def test_audit_with_ai_is_a_full_report(fake_ai):
    response = _audit(text="1. To withdraw consent, send a signed letter by post.\n\n2. We sell shoes.")
    result = response.json()
    assert (result["mode"], result["mode_reason"], result["model"]) == ("full", None, "claude-opus-5-5")
    assert result["score"]["estimated"] is False
    finding = result["findings"][0]
    assert finding["source"] == "ai" and finding["verdict"] == "non_compliant"
    assert finding["evidence"]["text"] == "send a signed letter by post"
    assert finding["suggested_rewrite"] == "Withdraw any time from Settings."
    assert result["counts"]["critical"] >= 1
    assert result["usage"]["requests"] == 1
    assert not any("keyword" in w for w in result["warnings"])


def test_segment_api_is_unchanged():
    response = client.post("/api/segment", data={"text": "1. First clause.\n\n2. Second clause."})
    assert response.status_code == 200
    assert set(response.json()) == {"source", "text", "clauses", "warnings"}
