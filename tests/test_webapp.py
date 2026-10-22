import html
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser

from pdf_builder import build_pdf
from webapp.main import MAX_PAGES, MAX_UPLOAD_BYTES, app

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "samples" / "sample_tos.txt"
SAMPLE_LINES = SAMPLE.read_text(encoding="utf-8").split("\n")
SPAN_RE = re.compile(r'<mark id="span-(\d+)"[^>]*>(.*?)</mark>', re.S)

client = TestClient(app)


def _upload(name, data, path="/api/segment"):
    return client.post(path, files={"file": (name, data)})


def test_index_shows_upload_form():
    response = client.get("/")
    assert response.status_code == 200
    assert 'enctype="multipart/form-data"' in response.text
    assert "discarded" in response.text


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


def test_results_page_highlights_exact_offsets():
    response = _upload("sample_tos.txt", SAMPLE.read_bytes(), path="/analyze")
    assert response.status_code == 200
    result = _upload("sample_tos.txt", SAMPLE.read_bytes()).json()
    spans = {int(i): html.unescape(body) for i, body in SPAN_RE.findall(response.text)}
    assert len(spans) == len(result["clauses"])
    for clause in result["clauses"]:
        assert spans[clause["index"]] == result["text"][clause["start"] : clause["end"]]


def test_document_text_is_escaped():
    attack = '<script>alert("x")</script> The Customer must pay all fees.'
    response = client.post("/analyze", data={"text": attack})
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text


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


def test_oversized_upload_on_page_shows_form_with_error():
    response = _upload("big.txt", b"a" * (MAX_UPLOAD_BYTES + 1), path="/analyze")
    assert response.status_code == 413
    assert "larger than" in response.text
    assert 'enctype="multipart/form-data"' in response.text


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


def test_warns_about_long_clauses_and_missing_numbers():
    long_para = "The Customer agrees to the following terms. " * 40
    text = f"PRIVACY\n\n{long_para}\n\nFEES\n\nFees apply.\n\nTERMINATION\n\nYou may cancel."
    response = client.post("/analyze", data={"text": text})
    assert "longer than 1500 characters" in response.text
    assert "No section numbers were found" in response.text
    assert '<span class="badge">long</span>' in response.text
