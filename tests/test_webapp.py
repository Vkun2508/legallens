import html
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape
from starlette.formparsers import MultiPartParser

from pdf_builder import build_pdf
from webapp.main import MAX_PAGES, MAX_UPLOAD_BYTES, SAMPLE_TEXT, app

DATA = Path(__file__).resolve().parent.parent / "data" / "samples"
SAMPLE = DATA / "sample_tos.txt"  # the v1 agreement, still used for the segmentation API
SAMPLE_LINES = SAMPLE.read_text(encoding="utf-8").split("\n")
POLICY = DATA / "sample_privacy_policy.txt"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "policies"
SPAN_RE = re.compile(r'<span class="clause-text" id="span-(\d+)">(.*?)</span>', re.S)
TAG_RE = re.compile(r"<[^>]+>")

client = TestClient(app)


def _upload(name, data, path="/api/segment", **form):
    return client.post(path, files={"file": (name, data)}, data=form or None)


def _audit_page(text, **form):
    return client.post("/audit", data={"text": text, **form})


def _section(page, start_marker, end_marker):
    start = page.index(start_marker)
    return page[start : page.index(end_marker, start)]


# ---------- Homepage ----------


def test_index_shows_the_audit_form():
    page = client.get("/").text
    h1 = _section(page, '<h1 id="hero-title">', "</h1>")
    assert " ".join(TAG_RE.sub(" ", h1).split()) == "What's missing from your privacy policy?"
    assert "<title>LegalLens: is your privacy policy DPDP-ready?</title>" in page
    assert re.search(r'action="[^"]*/audit"', page) and 'enctype="multipart/form-data"' in page
    assert "discarded" in page  # the privacy promise still holds: keyword mode sends nothing anywhere
    assert re.findall(r'name="business_type" value="(\w+)"', page) == ["app", "ecommerce", "marketplace"]
    assert 'value="app" checked' in page
    assert re.findall(r'name="goal" value="(\w+)"', page) == ["prelaunch", "live", "quick"]
    assert 'name="goal" value="quick" checked' in page  # the free option, where "Scan it free" lands
    # The hero has no address box: its row picks the upload form's file, then sends the visitor to the form.
    assert 'name="url"' not in page
    assert '<label class="scan-pick" for="file-input">' in page and 'id="scan-go"' in page
    # The page is dark only, so no toggle.
    assert 'id="theme-toggle"' not in page


def test_index_scan_shows_real_audit_output():
    page = client.get("/").text
    scan = _section(page, '<section class="scan" id="scan"', "</section>")
    # The sample's real audit: score, counts and rulebook come from the engine.
    assert 'data-score="57" data-issues="6" data-missing="10" data-clauses="11"' in scan
    assert "Estimated score 57 / 100" in scan and "rulebook 2026.11-draft.2" in scan
    assert "33 rules, 3 laws" in scan
    # The countdown to the date most DPDP duties apply, taken from the rulebook.
    assert re.search(r'data-in-force="2027-05-13">\d+ days</b>to DPDP duties, 13 May 2027', scan)
    # Every clause is on the sheet; the ones with possible issues carry their evidence and section.
    assert scan.count('class="scan-card') == 12  # the title and 11 clauses
    assert scan.count("scan-card is-flag") == 5
    assert '<mark class="critical">withdraw consent, send a signed letter by registered post</mark>' in scan
    assert '<b>Critical</b><span>DPDP Act s.6(4)</span>' in scan
    assert '<span>Dark patterns, Annex 1 items 12 and 5</span>' in scan
    # Missing clauses open as slots after the clause they belong with.
    slots = re.findall(r'<div class="scan-slot (\w+)"[^>]*>.*?<span>(.*?)</span><small>(.*?)</small>', scan)
    assert slots == [
        ("critical", "Parental consent for under-18s", "DPDP Act s.9(1), critical"),
        ("major", "Telling users and the Board about a breach", "DPDP Act s.8(6), major"),
        ("major", "How to complain to the Data Protection Board", "DPDP Act s.5(1)(iii), major"),
    ]
    assert scan.index("2. What we collect") < scan.index("Parental consent for under-18s") < scan.index("3. Your consent")
    # Screen readers get the same findings as a list.
    assert "Critical, possible issue: Withdrawing consent must be as easy as giving it (DPDP Act s.6(4))" in scan
    # The read's close-ups: the hard-to-withdraw consent clause, then the first missing clause.
    assert re.search(r'<article class="scan-card is-flag" data-findings="1" data-focus="1">\s*.*?4\. Withdrawing consent', scan, re.S)
    assert '<div class="scan-slot critical" data-focus="2">' in scan
    v1 = _section(scan, 'data-v="1"', "</div>")
    assert "Withdrawing consent must be as easy as giving it." in v1 and "DPDP Act s.6(4), possible issue" in v1
    assert "send a signed letter by registered post" in v1
    v2 = _section(scan, 'data-v="2"', "</div>")
    assert "Not found" in v2 and "Children (under 18) need verifiable parental consent." in v2
    assert "DPDP Act s.9(1), critical" in v2
    # The v3 lens and drifting backdrop are gone.
    assert 'class="lens"' not in page and "scanfield" not in page


def test_index_offers_the_full_sample_report():
    page = client.get("/").text
    sample = _section(page, '<form id="sample-form"', "</form>")
    assert re.search(r'action="[^"]*/audit"', sample) and "Kettle Privacy Policy" in sample
    assert page.count('form="sample-form"') == 2  # the nav link and the result's second action


def test_index_explains_how_it_works_with_the_sample():
    page = client.get("/").text
    how = _section(page, 'id="how-title"', "</section>")
    assert [b for b in re.findall(r"<li><b>(\w+)</b>", how)] == ["Read", "Check", "Fix"]
    assert "compared with 33 rules" in how
    # One real clause from the sample, marked up: the flagged wording struck, the section, the fix.
    assert "<del>withdraw consent, send a signed letter by registered post</del>" in how
    assert "Critical<span class=\"tier-qualifier\">, possible issue</span>" in how
    assert "<ins>You can withdraw your consent at any time, as easily as you gave it" in how


def test_index_shows_the_deadline_pricing_and_questions():
    page = client.get("/").text
    deadline = _section(page, 'id="deadline-title"', "</section>")
    assert re.search(r'<span class="ll-days">\d+ days</span> <span class="ll-until">until 13 May 2027</span>', deadline)
    pricing = _section(page, 'id="pricing-title"', "</section>")
    assert "Your first three check-ups are free" in pricing
    # Cheapest first: three free quick check-ups, then Monitoring; the full reviews are the Full audit report.
    assert re.findall(r"<dt>([^<]+)</dt>", pricing) == ["Quick check-up", "Monitoring", "Full audit report"]
    assert re.findall(r'<dd class="ll-plan-price">([^<]+)', pricing) == ["₹0 ", "about ₹1,999 ", "about ₹4,999 "]
    assert "Paid plans open after launch" in pricing  # pre-launch: no claim that they can be bought today
    assert "until then every review is free" in pricing
    faq = _section(page, 'id="faq-title"', "</section>")
    assert "Is this legal advice?" in faq and "never violations" in faq
    assert '<p class="ll-footer-name" aria-hidden="true">LegalLens</p>' in page


def test_review_options_name_their_plan_and_the_free_one_is_preselected():
    form = _section(client.get("/").text, 'id="upload-form"', "</form>")
    assert 'name="goal" value="quick" checked' in form
    assert form.count('<span class="hint choice-plan">In the Full audit report</span>') == 2
    assert '<span class="hint choice-plan">Free for your first 3, then Monitoring</span>' in form


def test_index_lists_the_laws_from_the_rulebook():
    page = client.get("/").text
    table = _section(page, 'id="checks-title"', "</section>")
    assert table.count('<th scope="row">') == 3
    assert "Digital Personal Data Protection Act, 2023" in table
    assert "Applies to online stores and marketplaces" in table
    assert "+ 8 to check by hand" in table


def test_index_shows_one_rule_and_a_draft_fix_from_the_sample():
    page = client.get("/").text
    rule = _section(page, 'class="ll-rule"', "</figure>")
    assert "Children (under 18) need verifiable parental consent" in rule
    assert "DPDP Act s.9(1), DPDP Rules r.10" in rule
    assert "obtain verifiable consent of the parent" in rule
    fix = _section(page, 'class="ll-file"', "</figure>")
    assert "6. Free trial" in fix
    assert "LegalLens: possible issue under Dark Patterns Guidelines, Annex 1, item 12" in fix
    assert "item 12, SaaS billing (silent recurring charges).</b>" in fix
    assert "item 5, subscription trap.</b>" in fix


def test_analyze_page_is_gone():
    assert client.post("/analyze", data={"text": "1. Some text."}).status_code == 404


# ---------- Segmentation API (unchanged from v1) ----------


def test_text_upload_returns_clauses():
    response = _upload("sample_tos.txt", SAMPLE.read_bytes())
    assert response.status_code == 200
    result = response.json()
    assert result["source"] == "sample_tos.txt"
    assert [(c["number"], c["heading"]) for c in result["clauses"]][1:3] == [
        ("1.1", "Definitions"),
        ("1.2", "Definitions"),
    ]
    assert len(result["clauses"]) == 9


def test_pdf_upload_returns_clauses():
    pdf = build_pdf([SAMPLE_LINES[:26], SAMPLE_LINES[26:]])
    result = _upload("sample_tos.pdf", pdf).json()
    assert len(result["clauses"]) == 9
    assert result["clauses"][5]["number"] == "3"
    assert result["clauses"][5]["heading"] == "Data Sharing"
    assert result["warnings"] == []


def test_pasted_text_is_analyzed():
    response = client.post("/api/segment", data={"text": "1. You must pay monthly.\n2. You may cancel."})
    assert [c["number"] for c in response.json()["clauses"]] == ["1", "2"]


@pytest.mark.parametrize(
    "files, data",
    [
        (None, {}),  # neither
        ({"file": ("a.txt", b"1. Text.")}, {"text": "Also pasted."}),  # both
    ],
)
def test_requires_exactly_one_input(files, data):
    response = client.post("/api/segment", files=files, data=data)
    assert response.status_code == 400
    assert "one file or paste text" in response.json()["detail"]


def test_rejects_unsupported_file_type():
    response = _upload("contract.docx", b"PK\x03\x04")
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_rejects_file_that_is_not_really_a_pdf():
    response = _upload("contract.pdf", b"<html>not a pdf</html>")
    assert response.status_code == 400
    assert "not a PDF" in response.json()["detail"]


def test_rejects_damaged_pdf():
    response = _upload("contract.pdf", b"%PDF-1.4\nthis is not a valid pdf body")
    assert response.status_code == 400
    assert "could not be read" in response.json()["detail"]


def test_rejects_oversized_upload():
    response = _upload("big.txt", b"a" * (MAX_UPLOAD_BYTES + 1))
    assert response.status_code == 413


def test_rejects_pdf_with_too_many_pages():
    response = _upload("long.pdf", build_pdf([[]] * (MAX_PAGES + 1)))
    assert response.status_code == 413
    assert f"limit is {MAX_PAGES}" in response.json()["detail"]


def test_accepted_uploads_stay_in_memory():
    # Starlette spools uploads above spool_max_size to a temporary file on disk.
    assert MultiPartParser.spool_max_size >= MAX_UPLOAD_BYTES


def test_pdf_without_text_warns_about_scans():
    result = _upload("scan.pdf", build_pdf([[], []])).json()
    assert result["clauses"] == []
    assert "scanned PDF" in result["warnings"][0]


def test_api_includes_risk_for_each_clause():
    result = _upload("sample_tos.txt", SAMPLE.read_bytes()).json()
    data_sharing = result["clauses"][5]
    assert data_sharing["risk"]["tier"] == "high"
    assert data_sharing["risk"]["categories"] == ["data_sharing"]
    evidence = data_sharing["risk"]["evidence"][0]
    assert data_sharing["text"][evidence["start"] : evidence["end"]] == evidence["text"]


# ---------- Audit results page ----------


def test_audit_page_highlights_exact_offsets():
    page = _audit_page(SAMPLE_TEXT).text
    result = client.post("/api/audit", data={"text": SAMPLE_TEXT}).json()
    # Evidence is marked inside each span; the text without tags is the exact clause span.
    spans = {int(i): html.unescape(TAG_RE.sub("", body)) for i, body in SPAN_RE.findall(page)}
    assert len(spans) == len(result["clauses"]) == 11
    for clause in result["clauses"]:
        assert spans[clause["index"]] == result["text"][clause["start"] : clause["end"]]


def test_audit_page_header_shows_estimated_score_and_status():
    page = _audit_page(SAMPLE_TEXT).text
    result = client.post("/api/audit", data={"text": SAMPLE_TEXT}).json()
    head = _section(page, '<header class="results-head', "</header>")
    assert '<span class="score-label">Estimated score</span>' in head
    assert f'<span class="score-value">{result["score"]["value"]}</span>' in head
    assert "11 of 27 rules met." in head
    assert "10 required clauses are missing and 6 possible issues to check in 5 clauses." in head
    assert "Missing or not met by severity: 1 critical, 6 major and 3 minor." in head
    assert 'id="print-summary"' in head and "Print report" in head
    assert '<button type="button" class="button" id="download-fixes" aria-describedby="fixes-hint" hidden>' in head
    assert "A keyword check, not a legal review." in page
    assert "AI review" not in page  # the free product never talks about a feature it doesn't run


def test_audit_page_lists_each_missing_clause_once_in_the_plan():
    page = _audit_page(SAMPLE_TEXT).text
    result = client.post("/api/audit", data={"text": SAMPLE_TEXT}).json()
    # One part: the action plan is the only list of clauses to add, each with its detail in place.
    assert 'id="missing-title"' not in page
    plan = _section(page, 'id="plan-title"', "</section>")
    assert plan.count('<li class="missing-item" id="missing-') == len(result["missing"]) == 10
    # Most severe first: the children's-data rule is the only critical one.
    assert plan.index("Children (under 18) need verifiable parental consent") < plan.index("Explains the right to nominate someone")
    assert "DPDP Act s.9(1)" in plan and "Checked against the official text" in plan
    assert "Good practice: the law sets this duty" in plan
    assert plan.count('<details class="wording">') == 10
    # Without JS the wording is still there to select; the copy button is revealed by app.js.
    assert 'class="button button-small copy-button" data-copy="wording-missing-dpdp.children.parental_consent" hidden' in plan
    screen = page[: page.index('<section class="print-report">')]
    for m in result["missing"]:
        assert screen.count(f'id="missing-{m["rule_id"]}"') == 1
        assert screen.count(str(escape(m["title"]))) == 1


def test_audit_page_margin_notes_cite_the_law():
    page = _audit_page(SAMPLE_TEXT).text
    assert page.count('class="row row-clause tier-high"') == 2  # consent by use, hard withdrawal
    assert 'data-filter="high" data-label="Critical" aria-pressed="false"' in page
    withdrawal = _section(page, 'id="clause-3"', "</article>")
    assert "Critical<span class=\"tier-qualifier\">, possible issue</span>" in withdrawal
    assert "Withdrawing consent must be as easy as giving it" in withdrawal
    assert "DPDP Act s.6(4)<span class=\"citation-also\">, also DPDP Rules r.3(c)(i)</span>" in withdrawal
    assert '<mark class="hit" title="Withdrawing consent must be as easy as giving it">' in withdrawal
    assert 'data-copy="wording-f' in withdrawal
    contact = _section(page, 'id="clause-10"', "</article>")
    assert '<span class="note-covers-label">Meets</span>' in contact and "No issues found" in contact


def test_audit_page_lists_screen_checks_and_export():
    page = _audit_page(SAMPLE_TEXT).text
    screens = _section(page, 'id="screens-title"', "</section>")
    assert screens.count("<li>") == 8 and "False urgency" in screens
    assert 'id="download-json"' in page and "/api/audit" in page
    data = json.loads(_section(page, '<script type="application/json" id="result-data">', "</script>").split(">", 1)[1])
    assert data["mode"] == "partial" and len(data["missing"]) == 10 and data["text"]


def test_print_report_lists_missing_issues_and_checks():
    page = _audit_page(SAMPLE_TEXT).text
    report = page[page.index('<section class="print-report">') :]
    assert "LegalLens compliance audit" in report
    assert re.findall(r'<h2 class="print-tier[^"]*">([^<]+)', report) == [
        "Action plan: fixing a live policy", "Critical possible issues ", "Major possible issues ", "Check your app's screens too ",
    ]
    assert report.count('<article class="print-clause tier-') == 6  # each possible issue
    # The plan carries the wording for each of the 10 clauses to add; the issues carry their own.
    assert report.count("<strong>Suggested wording:</strong>") == 10 + 6
    assert "compliance assistance, not legal advice" in report


def test_audit_page_respects_business_type():
    terms = (FIXTURES / "marketplace_terms.md").read_text(encoding="utf-8")
    page = _audit_page(terms, business_type="marketplace").text
    plan = _section(page, 'id="plan-title"', "</section>")
    assert "Names a grievance officer with contact details and timelines" in plan
    assert "Shows seller details on a marketplace" in plan


def test_document_text_is_escaped():
    attack = '<script>alert("x")</script> The Customer must pay all fees.'
    page = _audit_page(attack).text
    assert "<script>alert" not in page
    assert "&lt;script&gt;alert" in page


def test_bad_input_on_the_page_shows_the_form_with_an_error():
    response = _audit_page("   ")
    assert response.status_code == 400
    assert "This policy couldn't be audited." in response.text
    assert re.search(r'action="[^"]*/audit"', response.text)
    response = _audit_page("Some policy.", business_type="bank")
    assert response.status_code == 400 and "business_type" in response.text


def test_a_failed_upload_keeps_the_input_and_shows_the_error_by_the_form():
    response = _audit_page("1. Our pasted policy text.", business_type="bank")
    assert response.status_code == 400
    page = response.text
    form = _section(page, 'id="upload-form"', "</form>")
    assert "1. Our pasted policy text.</textarea>" in form
    assert 'id="upload-error" role="alert" tabindex="-1"><strong>This policy couldn\'t be audited.</strong>' in page
    assert 'class="scan-error"' not in page


def test_the_business_type_choice_survives_an_error():
    response = _audit_page("", business_type="marketplace")
    form = _section(response.text, 'id="upload-form"', "</form>")
    assert re.search(r'value="marketplace" checked', form)
    assert not re.search(r'value="app" checked', form)


def test_the_goal_choice_survives_an_error():
    response = _audit_page("", goal="quick")
    form = _section(response.text, 'id="upload-form"', "</form>")
    assert 'name="goal" value="quick" checked' in form
    assert 'name="goal" value="live" checked' not in form


def test_audit_page_shows_the_action_plan_for_the_goal():
    page = _audit_page(SAMPLE_TEXT, goal="quick").text
    result = client.post("/api/audit", data={"text": SAMPLE_TEXT}).json()
    plan = _section(page, 'id="plan-title"', "</section>")
    assert "Do these first" in plan
    top, rest = plan.split('<details class="wording plan-rest">')
    assert 1 <= top.count('class="missing-item"') <= 5
    # The clauses to add beyond the top five wait in a disclosure, so each still appears once.
    shown = top.count('<li class="missing-item" id="missing-')
    assert f"{len(result['missing']) - shown} more clauses to add" in rest
    assert plan.count('<li class="missing-item" id="missing-') == len(result["missing"])
    # A reword or check links to the flagged clause in the document.
    hrefs = re.findall(r'<a href="#([^"]+)">', plan)
    assert hrefs and all(f'id="{h}"' in page for h in hrefs)
    assert "Watch out for" in plan and "Keep it in shape" not in plan


def test_the_live_plan_groups_fixes_by_when():
    page = _audit_page(SAMPLE_TEXT).text
    plan = _section(page, 'id="plan-title"', "</section>")
    assert "Fix now" in plan or "Before " in plan
    assert "Keep it in shape" in plan and "Alongside the fixes" in plan


def test_pages_carry_the_new_mark_and_tab_icon():
    for page in (client.get("/").text, _audit_page(SAMPLE_TEXT).text):
        assert '<rect x="5" y="3" width="14" height="18"/><path d="M2 12h20"/>' in page
        assert "favicon.svg" in page
        assert "§</text>" not in page and "caslon" not in page.lower()


def test_unknown_pages_get_a_page_and_the_api_keeps_json():
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "This page isn't here" in response.text and "text/html" in response.headers["content-type"]
    response = client.get("/api/no-such-thing")
    assert response.status_code == 404 and response.json() == {"detail": "Not Found"}


def test_oversized_upload_on_page_shows_form_with_error():
    response = _upload("big.txt", b"a" * (MAX_UPLOAD_BYTES + 1), path="/audit")
    assert response.status_code == 413
    assert "larger than" in response.text
    assert 'enctype="multipart/form-data"' in response.text


def test_sample_policy_form_audits_the_bundled_sample():
    response = _audit_page(SAMPLE_TEXT)
    assert response.status_code == 200
    assert response.text.count('class="clause-text" id="span-') == 11
    assert "scanfield" not in response.text  # the scanning backdrop is for the landing page only


def test_warns_about_long_clauses_and_missing_numbers():
    long_para = "The Customer agrees to the following terms. " * 40
    text = f"PRIVACY\n\n{long_para}\n\nFEES\n\nFees apply.\n\nTERMINATION\n\nYou may cancel."
    page = _audit_page(text).text
    assert "longer than 1500 characters" in page
    assert "No section numbers were found" in page
    assert '<span class="badge">long</span>' in page
