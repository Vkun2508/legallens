"""Rebuild legallens/compliance/unfair_tos/ from the LexGLUE UNFAIR-ToS dataset.

Reproduces the LegalLens Colab classical baseline (word_balanced candidate,
per-label validation thresholds), asserts its recorded metrics, exports the
model as portable data files, checks the standard-library engine against
scikit-learn, and writes tests/fixtures/unfair_tos_parity.json.

Dev-only. Run in a separate Python 3.13 venv:
    pip install -r scripts/requirements-model.txt
    python scripts/build_unfair_model.py
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import platform
import random
import sys
from pathlib import Path

import numpy as np
import scipy
import sklearn
from datasets import load_dataset
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    multilabel_confusion_matrix,
    precision_score,
    recall_score,
)
from sklearn.multiclass import OneVsRestClassifier

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "legallens" / "compliance" / "unfair_terms.py"
EXPORT_DIR = ROOT / "legallens" / "compliance" / "unfair_tos"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "unfair_tos_parity.json"
SEED = 42

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
EXPECTED_SIZES = (5532, 2275, 1607)
EXPECTED_VALIDATION = {
    "global_macro_f1": 0.690818,
    "per_label_macro_f1": 0.707592,
    "per_label_micro_f1": 0.698990,
    "fixed_050_macro_f1": 0.615641,
}
EXPECTED_THRESHOLDS = [0.8, 0.6, 0.8, 0.7, 0.75, 0.65, 0.6, 0.7]
EXPECTED_TEST = {
    "micro_precision": 0.733333,
    "micro_recall": 0.709677,
    "micro_f1": 0.721311,
    "macro_precision": 0.765326,
    "macro_recall": 0.734820,
    "macro_f1": 0.738597,
    "weighted_f1": 0.724358,
    "exact_match_accuracy": 0.947106,
    "macro_average_precision": 0.819555,
    "micro_average_precision": 0.760156,
}
EXPECTED_CONFUSION = {  # label: (tn, fp, fn, tp)
    "Limitation of liability": (1565, 4, 12, 26),
    "Unilateral termination": (1550, 19, 8, 30),
    "Unilateral change": (1563, 6, 17, 21),
    "Content removal": (1583, 11, 3, 10),
    "Contract by using": (1581, 3, 7, 16),
    "Choice of law": (1592, 2, 1, 12),
    "Jurisdiction": (1589, 2, 4, 12),
    "Arbitration": (1599, 1, 2, 5),
}
PARITY_TEXTS = [
    "To the fullest extent permitted by law, we shall not be liable for any indirect, incidental or consequential damages arising out of your use of the service.",
    "Our total liability to you for any claim shall not exceed the amount you paid us in the twelve months before the claim.",
    "The service is provided on an as is basis and we accept no responsibility for any loss of data.",
    "We may suspend or terminate your account at any time, for any reason, without notice.",
    "We reserve the right to discontinue the service or close your account at our sole discretion.",
    "We may modify these terms at any time, and changes take effect as soon as they are posted on this page.",
    "We reserve the right to change our prices and features without prior notice to you.",
    "Your continued use of the app after we update this policy means you accept the revised terms.",
    "We may remove or disable access to any content you upload if we believe it violates these terms.",
    "We can delete your posts, comments or listings at our sole discretion and without explanation.",
    "By accessing or using the website, you agree to be bound by these terms of service.",
    "If you do not agree with these terms, you must not use our services.",
    "These terms are governed by and construed in accordance with the laws of the State of California.",
    "This agreement shall be governed by the laws of India, without regard to its conflict of law provisions.",
    "You agree that any dispute shall be brought exclusively in the courts located in Bengaluru, Karnataka.",
    "The courts of England and Wales have exclusive jurisdiction over any claim arising from these terms.",
    "Any dispute arising out of these terms will be resolved by binding arbitration, and you waive your right to a jury trial.",
    "All claims must be submitted to individual arbitration under the rules of the American Arbitration Association.",
    "We collect your name, email address and phone number when you create an account.",
    "You can contact our grievance officer at grievance@example.com for any questions.",
    "Orders are usually delivered within five to seven business days.",
    "Please read this privacy policy carefully before using the app.",
    "We use cookies to remember your preferences and keep you signed in.",
    "",
    "a b c",
    "zzqx flurbish quonk vexillate",
    "Café owners résumé naïve façade — accented words must be stripped the same way.",
    "WE MAY TERMINATE YOUR ACCOUNT AT ANY TIME WITHOUT NOTICE.",
    "We’ll “update” these Terms from time to time — check back often.",
    "Section 12.3(b) limits our liability to INR 5,000 or 100 USD, whichever is lower.",
    "Tämä palvelu ① ② ③ 東京 مرحبا",
    "terminate terminate terminate terminate terminate",
    "the the the",
    "  \n\t We   may\nchange\tthese terms.  ",
    "e.g. the company may, i.e. at its discretion, end the contract.",
    "Arbitration.",
    "We may change these terms, suspend your account, remove your content and any dispute will be settled by arbitration in Singapore under Singapore law.",
    "You will indemnify us against all claims, losses and expenses arising from your breach of these terms.",
    "Subscriptions renew automatically unless you cancel at least 24 hours before the end of the period.",
    "In no event shall the company be liable for damages, even if advised of the possibility of such damages.",
]
NOTE = (
    "Indicators of resemblance to UNFAIR-ToS benchmark categories, not legal conclusions. "
    "A sentence with no predicted category is not thereby fair."
)


def to_multihot(ds, num_labels):
    y = np.zeros((len(ds), num_labels), dtype=np.int32)
    for i, row in enumerate(ds):
        for label_id in row["labels"]:
            y[i, label_id] = 1
    return y


def check(failures, name, actual, expected, tol):
    if abs(actual - expected) > tol:
        failures.append(f"{name}: got {actual!r}, expected {expected!r} (diff {actual - expected:+.3e})")


def write_gzip(path, data: bytes):
    with path.open("wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0, compresslevel=9) as gz:
        gz.write(data)


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def load_engine():
    # Loaded by path: importing legallens.compliance pulls in pydantic and yaml.
    spec = importlib.util.spec_from_file_location("unfair_terms_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolves annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def main():
    random.seed(SEED)
    np.random.seed(SEED)

    # --- Train (the notebook's word_balanced candidate) -------------------------------
    dataset = load_dataset("coastalcph/lex_glue", "unfair_tos")
    train_ds, val_ds, test_ds = dataset["train"], dataset["validation"], dataset["test"]
    label_names = train_ds.features["labels"].feature.names
    num_labels = len(label_names)
    y_train, y_val, y_test = (to_multihot(ds, num_labels) for ds in (train_ds, val_ds, test_ds))
    X_train_text = [r["text"] for r in train_ds]
    X_val_text = [r["text"] for r in val_ds]
    X_test_text = [r["text"] for r in test_ds]

    vec = TfidfVectorizer(
        lowercase=True, strip_accents="unicode", analyzer="word", ngram_range=(1, 2), min_df=2,
        max_features=100_000, sublinear_tf=True, norm="l2", dtype=np.float32,
    )
    Xtr = vec.fit_transform(X_train_text)
    Xv = vec.transform(X_val_text)
    clf = OneVsRestClassifier(
        LogisticRegression(class_weight="balanced", solver="liblinear", max_iter=2000, random_state=SEED),
        n_jobs=-1,
    )
    clf.fit(Xtr, y_train)
    val_probs = clf.predict_proba(Xv)

    grid = np.arange(0.05, 0.96, 0.05)
    global_scores = [f1_score(y_val, (val_probs >= t).astype(int), average="macro", zero_division=0) for t in grid]
    global_t = float(grid[int(np.argmax(global_scores))])
    thresholds = np.array([
        float(grid[int(np.argmax([
            f1_score(y_val[:, j], (val_probs[:, j] >= t).astype(int), zero_division=0) for t in grid
        ]))])
        for j in range(num_labels)
    ])
    val_pred = (val_probs >= thresholds.reshape(1, -1)).astype(int)
    validation = {
        "global_threshold": global_t,
        "global_macro_f1": float(max(global_scores)),
        "per_label_macro_f1": float(f1_score(y_val, val_pred, average="macro", zero_division=0)),
        "per_label_micro_f1": float(f1_score(y_val, val_pred, average="micro", zero_division=0)),
        "fixed_050_macro_f1": float(f1_score(y_val, (val_probs >= 0.5).astype(int), average="macro", zero_division=0)),
    }

    test_probs = clf.predict_proba(vec.transform(X_test_text))
    y_pred = (test_probs >= thresholds.reshape(1, -1)).astype(int)
    ap = [average_precision_score(y_test[:, j], test_probs[:, j]) for j in range(num_labels)]
    test = {
        "micro_precision": precision_score(y_test, y_pred, average="micro", zero_division=0),
        "micro_recall": recall_score(y_test, y_pred, average="micro", zero_division=0),
        "micro_f1": f1_score(y_test, y_pred, average="micro", zero_division=0),
        "macro_precision": precision_score(y_test, y_pred, average="macro", zero_division=0),
        "macro_recall": recall_score(y_test, y_pred, average="macro", zero_division=0),
        "macro_f1": f1_score(y_test, y_pred, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_test, y_pred, average="weighted", zero_division=0),
        "exact_match_accuracy": accuracy_score(y_test, y_pred),
        "macro_average_precision": float(np.mean(ap)),
        "micro_average_precision": average_precision_score(y_test.ravel(), test_probs.ravel()),
    }
    test = {k: float(v) for k, v in test.items()}

    def confusion_of(pred):
        return {
            label: tuple(int(v) for v in m.ravel())  # sklearn order: tn, fp, fn, tp
            for label, m in zip(label_names, multilabel_confusion_matrix(y_test, pred))
        }

    confusion = confusion_of(y_pred)

    # --- Assert the recorded notebook values -------------------------------------------
    failures = []
    sizes = (len(train_ds), len(val_ds), len(test_ds))
    if sizes != EXPECTED_SIZES:
        failures.append(f"split sizes: got {sizes}, expected {EXPECTED_SIZES}")
    if list(label_names) != LABELS:
        failures.append(f"labels: got {list(label_names)}, expected {LABELS}")
    for name, expected in EXPECTED_VALIDATION.items():
        check(failures, f"validation.{name}", validation[name], expected, 5e-7)
    for j, expected in enumerate(EXPECTED_THRESHOLDS):
        check(failures, f"threshold[{j}]", float(thresholds[j]), expected, 1e-9)
    for name, expected in EXPECTED_TEST.items():
        check(failures, f"test.{name}", test[name], expected, 5e-7)
    if confusion != EXPECTED_CONFUSION:
        for label in LABELS:
            if confusion.get(label) != EXPECTED_CONFUSION[label]:
                failures.append(f"confusion[{label}]: got {confusion.get(label)}, expected {EXPECTED_CONFUSION[label]}")
    print("validation:", {k: round(v, 6) for k, v in validation.items()})
    print("thresholds:", thresholds.tolist())
    print("test:", {k: round(v, 6) for k, v in test.items()})
    if failures:
        print("REPRODUCE: FAIL")
        for failure in failures:
            print("  " + failure)
        sys.exit(1)
    print("REPRODUCE: PASS")

    # --- Export -------------------------------------------------------------------------
    assert clf.multilabel_ is True
    for e in clf.estimators_:
        assert isinstance(e, LogisticRegression) and e.classes_.tolist() == [0, 1], e
    vocab = vec.vocabulary_
    n_features = len(vocab)
    assert sorted(vocab.values()) == list(range(n_features))
    terms = sorted(vocab, key=vocab.get)
    assert not any("\n" in t for t in terms)
    coef = np.vstack([e.coef_.ravel() for e in clf.estimators_])
    assert coef.shape == (num_labels, n_features)
    idf = np.asarray(vec.idf_)
    assert idf.shape == (n_features,)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_gzip(EXPORT_DIR / "vocab.txt.gz", ("\n".join(terms) + "\n").encode("utf-8"))
    weights = np.concatenate([idf.astype("<f4"), coef.astype("<f4").ravel(order="C")])
    write_gzip(EXPORT_DIR / "weights.f32.gz", weights.tobytes())
    files = {name: sha256(EXPORT_DIR / name) for name in ("vocab.txt.gz", "weights.f32.gz")}

    meta = {
        "format_version": 1,
        "name": "tfidf-logreg-unfair-tos",
        "labels": list(label_names),
        "keys": KEYS,
        "thresholds": [float(t) for t in thresholds],
        "intercepts": [float(e.intercept_[0]) for e in clf.estimators_],
        "n_features": n_features,
        "vectorizer": {
            "lowercase": True,
            "strip_accents": "unicode",
            "analyzer": "word",
            "token_pattern": vec.token_pattern,
            "ngram_range": [1, 2],
            "sublinear_tf": True,
            "norm": "l2",
            "min_df": 2,
            "max_features": 100000,
        },
        "weights": {"dtype": "float32", "byteorder": "little", "layout": "idf[V] then coef[8][V] row-major"},
        "files": files,
        "provenance": {
            "dataset": "coastalcph/lex_glue",
            "config": "unfair_tos",
            "seed": SEED,
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "trained_by": "scripts/build_unfair_model.py, reproducing the LegalLens Colab classical baseline (word_balanced, validation_per_label)",
        },
        "metrics": {
            "validation": validation,
            "test": test,
            "test_confusion": {
                label: dict(zip(("tn", "fp", "fn", "tp"), counts)) for label, counts in confusion.items()
            },
        },
        "note": NOTE,
    }
    assert meta["vectorizer"]["token_pattern"] == r"(?u)\b\w\w+\b"
    write_json(EXPORT_DIR / "model.json", meta)

    # --- Parity: the stdlib engine on the exported files vs scikit-learn ---------------
    engine = load_engine()
    model = engine.load_model(EXPORT_DIR)
    engine_probs = np.array(model.predict_proba(X_test_text))
    max_diff = float(np.max(np.abs(engine_probs - test_probs)))
    engine_pred = (engine_probs >= thresholds.reshape(1, -1)).astype(int)
    decision_diffs = int(np.sum(engine_pred != y_pred))
    print(f"parity: max |p_engine - p_sklearn| = {max_diff:.3e}, decision differences = {decision_diffs}")
    assert max_diff <= 1e-5, max_diff
    assert decision_diffs == 0, decision_diffs
    assert confusion_of(engine_pred) == EXPECTED_CONFUSION
    print("PARITY: PASS")

    # --- Parity fixture for the repo's test suite ---------------------------------------
    fixture_probs = clf.predict_proba(vec.transform(PARITY_TEXTS))
    write_json(FIXTURE_PATH, {
        "model_files": files,
        "cases": [{"text": t, "probs": [float(p) for p in row]} for t, row in zip(PARITY_TEXTS, fixture_probs)],
    })
    for name in ("model.json", "vocab.txt.gz", "weights.f32.gz"):
        print(f"{name}: {(EXPORT_DIR / name).stat().st_size} bytes, sha256 {sha256(EXPORT_DIR / name)}")
    print(f"{FIXTURE_PATH.name}: sha256 {sha256(FIXTURE_PATH)}")


if __name__ == "__main__":
    main()
