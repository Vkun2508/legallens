import gzip
import hashlib
import json
import math
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from legallens import normalize_text, segment
from legallens.compliance import unfair_terms
from legallens.compliance.audit import audit
from legallens.compliance.evaluation import load_fixtures
from legallens.compliance.unfair_terms import (
    MODEL_DIR,
    NOTE,
    ModelLoadError,
    default_model,
    flag_clauses,
    load_model,
    split_sentences,
)
from webapp.main import app

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "unfair_tos_parity.json").read_text(encoding="utf-8"))
LABELS = [
    "Limitation of liability",
    "Unilateral termination",
    "Unilateral change",
    "Content removal",
    "Contract by using",
    "Choice of law",
    "Jurisdiction",
    "Arbitration",
]
KEYS = [
    "limitation_of_liability",
    "unilateral_termination",
    "unilateral_change",
    "content_removal",
    "contract_by_using",
    "choice_of_law",
    "jurisdiction",
    "arbitration",
]


@pytest.fixture(scope="module")
def model():
    return load_model()


def test_bundled_model_loads(model):
    cats = model.categories
    assert [c.label for c in cats] == LABELS
    assert [c.key for c in cats] == KEYS
    assert [round(c.threshold, 2) for c in cats] == [0.8, 0.6, 0.8, 0.7, 0.75, 0.65, 0.6, 0.7]
    assert all(c.suggestion for c in cats)
    assert 0 < model.n_features <= 100_000


def test_engine_matches_sklearn_parity_fixture(model):
    assert FIXTURE["model_files"] == model.meta["files"]
    texts = [case["text"] for case in FIXTURE["cases"]]
    for case, probs in zip(FIXTURE["cases"], model.predict_proba(texts)):
        assert max(abs(p - q) for p, q in zip(probs, case["probs"])) <= 1e-5, case["text"]
        for p, q, cat in zip(probs, case["probs"], model.categories):
            assert (p >= cat.threshold) == (q >= cat.threshold), (case["text"], cat.key)


@pytest.mark.parametrize("text", ["", "zzqx flurbish quonk vexillate"])
def test_text_without_known_words_gives_the_intercepts(model, text):
    assert model.vectorize(text) == {}
    (probs,) = model.predict_proba([text])
    for p, b, cat in zip(probs, model.meta["intercepts"], model.categories):
        assert abs(p - 1 / (1 + math.exp(-b))) <= 1e-12
        assert p < cat.threshold


def test_split_sentences():
    assert split_sentences("We may change these terms. You agree to them by signing up.") == [
        "We may change these terms.",
        "You agree to them by signing up.",
    ]
    assert split_sentences("We may, e.g. the company may end the contract.") == [
        "We may, e.g. the company may end the contract."
    ]
    assert split_sentences("Short one. We may end your account at any time. Ok then.") == [
        "We may end your account at any time."
    ]
    assert split_sentences("  We   may\nchange\tthese\n\nterms.  ") == ["We may change these terms."]


def _rewrite_meta(directory, **changes):
    path = directory / "model.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta.update(changes)
    path.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def _truncate_weights(directory):
    path = directory / "weights.f32.gz"
    path.write_bytes(gzip.compress(gzip.decompress(path.read_bytes())[:-4 * 10]))
    meta = json.loads((directory / "model.json").read_text(encoding="utf-8"))
    files = dict(meta["files"], **{"weights.f32.gz": hashlib.sha256(path.read_bytes()).hexdigest()})
    _rewrite_meta(directory, files=files)


@pytest.mark.parametrize(
    "corrupt, message",
    [
        (_truncate_weights, "weights hold"),
        (lambda d: _rewrite_meta(d, files={"vocab.txt.gz": "0" * 64, "weights.f32.gz": "0" * 64}), "sha256"),
        (lambda d: (d / "vocab.txt.gz").unlink(), "missing"),
        (lambda d: _rewrite_meta(d, format_version=2), "format_version"),
    ],
    ids=["truncated-weights", "wrong-sha", "missing-vocab", "format-version-2"],
)
def test_corrupt_model_raises(tmp_path, corrupt, message):
    directory = tmp_path / "unfair_tos"
    shutil.copytree(MODEL_DIR, directory)
    corrupt(directory)
    with pytest.raises(ModelLoadError, match=message):
        load_model(directory)


def test_default_model_is_a_singleton():
    assert default_model() is default_model()


def test_flag_clauses_on_sample_policy(model):
    text = normalize_text((ROOT / "data" / "samples" / "sample_tos.txt").read_text(encoding="utf-8"))
    clauses = segment(text)
    checked, flags = flag_clauses(model, text, clauses)

    assert checked > 0
    assert flags
    assert [f["id"] for f in flags] == [f"u{i}" for i in range(1, len(flags) + 1)]
    assert [f["clause_index"] for f in flags] == sorted(f["clause_index"] for f in flags)
    for f in flags:
        assert f["category"] in KEYS
        assert f["score"] >= f["threshold"]
        evidence = f["evidence"]
        if evidence is not None:
            clause = clauses[f["clause_index"]]
            assert clause.start <= evidence["start"] < evidence["end"] <= clause.end
            assert evidence["text"] == text[evidence["start"] : evidence["end"]]


# --- wiring into the audit: /api/audit only, never the score ---


def _sample_documents():
    docs = []
    for path in sorted((ROOT / "data" / "samples").glob("*.txt")):
        text = normalize_text(path.read_text(encoding="utf-8"))
        docs.append((path.stem, text, segment(text), "app"))
    docs += [(f.name, f.text, f.clauses, f.business_type) for f in load_fixtures()]
    return docs


DOCUMENTS = _sample_documents()
SAMPLE_TOS_TEXT = (ROOT / "data" / "samples" / "sample_tos.txt").read_text(encoding="utf-8")
client = TestClient(app)
UNAVAILABLE = {"status": "unavailable", "model": None, "note": NOTE, "sentences_checked": 0, "flags": []}


@pytest.mark.parametrize("name, text, clauses, business_type", DOCUMENTS, ids=[d[0] for d in DOCUMENTS])
def test_model_never_changes_the_audit(name, text, clauses, business_type):
    a = audit(text, clauses, business_type=business_type, mode="keyword").to_dict()
    b = audit(text, clauses, business_type=business_type, mode="keyword", unfair_terms=True).to_dict()
    assert "unfair_terms" not in a
    assert b.pop("unfair_terms")["status"] == "ok"
    assert a == b


def test_audit_without_the_flag_never_loads_the_model(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the unfair-terms model must not be used")

    monkeypatch.setattr(unfair_terms, "default_model", fail)
    monkeypatch.setattr(unfair_terms, "check_document", fail)
    monkeypatch.setattr("legallens.compliance.audit.check_document", fail)
    _, text, clauses, business_type = DOCUMENTS[0]
    report = audit(text, clauses, business_type=business_type, mode="keyword")
    assert report.unfair_terms is None


def test_audit_page_never_includes_the_model():
    response = client.post("/audit", data={"text": SAMPLE_TOS_TEXT})
    assert response.status_code == 200
    assert "unfair_terms" not in response.text


def _api_audit():
    response = client.post("/api/audit", data={"text": SAMPLE_TOS_TEXT})
    assert response.status_code == 200
    return response.json()


def test_api_audit_adds_only_the_unfair_terms_key(monkeypatch):
    data = _api_audit()
    monkeypatch.setenv("LEGALLENS_UNFAIR_MODEL", "off")
    baseline = _api_audit()
    assert baseline.pop("unfair_terms")["status"] == "disabled"
    assert set(data) - {"unfair_terms"} == set(baseline)
    for d in (data, baseline):
        d.pop("generated_at", None)
    result = data.pop("unfair_terms")
    assert data == baseline

    assert result["status"] == "ok"
    assert result["model"]["name"] == "tfidf-logreg-unfair-tos"
    assert result["model"]["test_macro_f1"] == 0.7386
    assert result["flags"]
    for flag in result["flags"]:
        assert set(flag) == {"id", "clause_index", "category", "label", "score", "threshold", "evidence", "suggestion"}


@pytest.mark.parametrize("target", ["default_model", "flag_clauses"])
def test_api_audit_survives_a_model_failure(monkeypatch, target):
    monkeypatch.setenv("LEGALLENS_UNFAIR_MODEL", "off")
    baseline_score = _api_audit()["score"]
    monkeypatch.delenv("LEGALLENS_UNFAIR_MODEL")
    error = ModelLoadError("boom") if target == "default_model" else RuntimeError("boom")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(unfair_terms, target, fail)
    data = _api_audit()
    assert data["unfair_terms"] == UNAVAILABLE
    assert data["score"] == baseline_score


@pytest.mark.parametrize("value", ["off", "0"])
def test_env_switch_disables_the_model(monkeypatch, value):
    monkeypatch.setenv("LEGALLENS_UNFAIR_MODEL", value)
    _, text, clauses, _ = DOCUMENTS[0]
    result = unfair_terms.check_document(text, clauses)
    assert result["status"] == "disabled"
    assert result["model"] is None
    assert result["flags"] == []
