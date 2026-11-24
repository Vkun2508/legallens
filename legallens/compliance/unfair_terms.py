"""Unfair-terms classifier: a standard-library engine for the bundled UNFAIR-ToS model.

The model (TF-IDF word 1-2 grams + one-vs-rest logistic regression) is trained by
`scripts/build_unfair_model.py` with scikit-learn 1.6.1 and exported to
`unfair_tos/`. This module reproduces scikit-learn's `predict_proba` without
numpy or scikit-learn, so the web app needs no extra dependency.

Predictions are indicators of resemblance to the UNFAIR-ToS benchmark
categories, not legal conclusions.

Import constraint: no top-level import from `legallens` or third-party packages.
The build script loads this file by path in a venv without pydantic or yaml.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import math
import os
import re
import sys
import threading
import time
import unicodedata
from array import array
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from legallens.segmentation import Clause

MODEL_DIR = Path(__file__).with_name("unfair_tos")

logger = logging.getLogger("legallens.compliance")
ENV_SWITCH = "LEGALLENS_UNFAIR_MODEL"  # "off", "0", "false" or "no" (any case) disables the model
NOTE = ("Indicators of resemblance to UNFAIR-ToS benchmark categories, not legal conclusions. "
        "A clause with no flag is not thereby fair. Not part of the compliance score.")

SUGGESTIONS: dict[str, str] = {
    "Limitation of liability": "Clarify the scope of excluded liability. Retain appropriate exceptions for liability that cannot legally be excluded and ensure limitations are proportionate.",
    "Unilateral termination": "Specify clear grounds for termination, provide reasonable notice and consider allowing users an opportunity to remedy a breach where appropriate.",
    "Unilateral change": "Provide advance notice of material changes, explain their impact on users and consider allowing users to discontinue the service where appropriate.",
    "Content removal": "Clearly define the circumstances in which content may be removed. Consider notifying affected users and providing an appropriate review mechanism.",
    "Contract by using": "Make acceptance clear through an accessible notice and affirmative acceptance mechanism rather than relying solely on continued use.",
    "Choice of law": "Clearly identify the governing law and explain its application while preserving mandatory legal protections.",
    "Jurisdiction": "Clearly specify the chosen jurisdiction while considering applicable consumer protections and mandatory legal rights.",
    "Arbitration": "Explain the arbitration process, applicable rules, costs, location and any statutory rights or exceptions available to users.",
}

_N_LABELS = 8
_TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=["“‘(]*[A-Z0-9])')


class ModelLoadError(Exception):
    """The bundled model files are missing, corrupt or inconsistent."""


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    threshold: float
    suggestion: str


def _strip_accents_unicode(s: str) -> str:
    # Same as sklearn.feature_extraction.text.strip_accents_unicode (1.6.1).
    try:
        s.encode("ASCII")
        return s
    except UnicodeEncodeError:
        return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _sigmoid(d: float) -> float:
    if d >= 0:
        return 1.0 / (1.0 + math.exp(-d))
    e = math.exp(d)
    return e / (1.0 + e)


class UnfairTermsModel:
    def __init__(self, meta: dict, terms: list[str], weights: array):
        n = meta["n_features"]
        self.meta = meta
        self.n_features = n
        self.categories = tuple(
            Category(key, label, float(t), SUGGESTIONS[label])
            for key, label, t in zip(meta["keys"], meta["labels"], meta["thresholds"])
        )
        self._index = {term: j for j, term in enumerate(terms)}
        self._idf = weights[:n]
        self._coef = weights[n:]  # flat, row-major (label, feature)
        self._intercepts = [float(b) for b in meta["intercepts"]]

    def vectorize(self, text: str) -> dict[int, float]:
        """TF-IDF features of `text` as {feature index: value}, as sklearn 1.6.1 computes them."""
        tokens = _TOKEN_RE.findall(_strip_accents_unicode(text.lower()))
        grams = tokens + [" ".join(tokens[i : i + 2]) for i in range(len(tokens) - 1)]
        counts = Counter(j for j in map(self._index.get, grams) if j is not None)
        values = {j: (1.0 + math.log(c)) * self._idf[j] for j, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in values.values()))
        return {j: v / norm for j, v in values.items()} if norm else {}

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]:
        n, coef = self.n_features, self._coef
        out = []
        for text in texts:
            d = list(self._intercepts)
            for j, x in self.vectorize(text).items():
                for k in range(_N_LABELS):
                    d[k] += x * coef[k * n + j]
            out.append([_sigmoid(v) for v in d])
        return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_model(directory: Path = MODEL_DIR) -> UnfairTermsModel:
    """Load and validate an exported model directory. Raises ModelLoadError on any problem."""
    directory = Path(directory)
    try:
        meta = json.loads((directory / "model.json").read_text(encoding="utf-8"))
        if meta.get("format_version") != 1:
            raise ModelLoadError(f"unsupported format_version {meta.get('format_version')!r} (expected 1)")
        for field in ("labels", "keys", "intercepts", "thresholds"):
            if not isinstance(meta.get(field), list) or len(meta[field]) != _N_LABELS:
                raise ModelLoadError(f"model.json '{field}' must list {_N_LABELS} values")
        if not all(isinstance(t, (int, float)) and 0 < t < 1 for t in meta["thresholds"]):
            raise ModelLoadError("every threshold must lie strictly between 0 and 1")
        missing = [label for label in meta["labels"] if label not in SUGGESTIONS]
        if missing:
            raise ModelLoadError(f"no suggestion for labels {missing}")
        n = meta.get("n_features")
        if not isinstance(n, int) or n <= 0:
            raise ModelLoadError("model.json 'n_features' must be a positive integer")

        files = meta.get("files") or {}
        for name in ("vocab.txt.gz", "weights.f32.gz"):
            path = directory / name
            if not path.is_file():
                raise ModelLoadError(f"missing model file {name}")
            if _sha256(path) != files.get(name):
                raise ModelLoadError(f"{name} does not match its sha256 in model.json")

        terms = gzip.decompress((directory / "vocab.txt.gz").read_bytes()).decode("utf-8").split("\n")
        if terms and terms[-1] == "":
            terms.pop()
        if len(terms) != n:
            raise ModelLoadError(f"vocab has {len(terms)} terms, expected n_features={n}")

        weights = array("f")
        weights.frombytes(gzip.decompress((directory / "weights.f32.gz").read_bytes()))
        if sys.byteorder != "little":
            weights.byteswap()
        if len(weights) != (1 + _N_LABELS) * n:
            raise ModelLoadError(f"weights hold {len(weights)} floats, expected {(1 + _N_LABELS) * n}")
        return UnfairTermsModel(meta, terms, weights)
    except ModelLoadError:
        raise
    except (OSError, ValueError, EOFError, KeyError, TypeError, AttributeError) as exc:
        # json.JSONDecodeError, UnicodeDecodeError and gzip.BadGzipFile are ValueError/OSError subclasses.
        raise ModelLoadError(f"could not load the unfair-terms model from {directory}: {exc}") from exc


_default: UnfairTermsModel | None = None
_default_lock = threading.Lock()


def default_model() -> UnfairTermsModel:
    """The bundled model, loaded once on first use. A failed load is retried on the next call."""
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = load_model()
    return _default


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = (part.strip() for part in _SENTENCE_SPLIT_RE.split(text))
    return [part for part in parts if len(part.split()) >= 4]


def flag_clauses(model: UnfairTermsModel, text: str, clauses: Sequence[Clause]) -> tuple[int, list[dict]]:
    """Flag clauses whose best sentence reaches a category's threshold.

    Returns (number of sentences checked, flags). Headings are never classified.
    """
    from legallens.compliance.report import locate

    owners: list[int] = []  # position in `clauses` of each sentence
    sentences: list[str] = []
    for pos, clause in enumerate(clauses):
        for sentence in split_sentences(clause.text):
            owners.append(pos)
            sentences.append(sentence)
    probs = model.predict_proba(sentences)

    best: dict[tuple[int, int], tuple[float, str]] = {}
    for pos, sentence, row in zip(owners, sentences, probs):
        for k, (p, category) in enumerate(zip(row, model.categories)):
            if p >= category.threshold and p > best.get((pos, k), (-1.0, ""))[0]:
                best[(pos, k)] = (p, sentence)

    flags = []
    for (pos, k), (p, sentence) in sorted(best.items(), key=lambda item: (item[0][0], -item[1][0], item[0][1])):
        clause, category = clauses[pos], model.categories[k]
        span = locate(sentence, text, clause.start, clause.end)
        flags.append(
            {
                "id": f"u{len(flags) + 1}",
                "clause_index": clause.index,
                "category": category.key,
                "label": category.label,
                "score": round(p, 4),
                "threshold": round(category.threshold, 4),
                "evidence": {"start": span[0], "end": span[1], "text": text[span[0] : span[1]]} if span else None,
                "suggestion": category.suggestion,
            }
        )
    return len(sentences), flags


def _empty(status: str) -> dict:
    return {"status": status, "model": None, "note": NOTE, "sentences_checked": 0, "flags": []}


def check_document(text: str, clauses: Sequence[Clause]) -> dict:
    """The `unfair_terms` section of an audit. Never raises: a model problem yields status "unavailable"."""
    if os.environ.get(ENV_SWITCH, "").strip().lower() in {"off", "0", "false", "no"}:
        return _empty("disabled")
    try:
        model = default_model()
        started = time.perf_counter()
        n, flags = flag_clauses(model, text, clauses)
        logger.info("unfair_terms: %d sentences, %d flags in %.2fs", n, len(flags), time.perf_counter() - started)
        meta = model.meta
        return {
            "status": "ok",
            "model": {"name": meta["name"], "format_version": meta["format_version"],
                      "dataset": "LexGLUE UNFAIR-ToS",
                      "test_macro_f1": round(meta["metrics"]["test"]["macro_f1"], 4)},
            "note": NOTE,
            "sentences_checked": n,
            "flags": flags,
        }
    except Exception as exc:
        logger.warning("unfair-terms model unavailable (%s: %s); the audit continues without it",
                       type(exc).__name__, exc)
        return _empty("unavailable")
