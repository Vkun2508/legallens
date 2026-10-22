"""LegalLens web demo: upload an agreement, see its clauses and their offsets.

Run locally with:  uvicorn webapp.main:app
(uvicorn listens on 127.0.0.1 by default; uploads may be real financial
agreements, so exposing it more widely is a separate decision.)

Uploads are processed in memory and discarded after the response: nothing is
written to disk or kept, and logs record sizes and counts, never content.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.formparsers import MultiPartParser

from legallens import Assessment, Clause, assess, load_bytes, normalize_text, segment
from legallens.risk import CATEGORIES, CATEGORY_BY_KEY, TIER_LABELS, TIERS

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PAGES = 200
ALLOWED_SUFFIXES = (".pdf", ".txt", ".md")
LONG_CLAUSE_CHARS = 1500
# Multipart framing around the file adds a little to the request size.
_MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
# A heading carried by this share of clauses is probably a document title.
_CARRIED_HEADING_SHARE = 0.4
_CARRIED_HEADING_MIN_CLAUSES = 5

# Starlette writes uploads above spool_max_size to a temporary file. Raising it
# to the upload limit keeps every accepted upload in memory; larger requests
# are rejected by size_limit() before the body is parsed.
MultiPartParser.spool_max_size = _MAX_REQUEST_BYTES

_HERE = Path(__file__).resolve().parent
SAMPLE_TEXT = (_HERE.parent / "data" / "samples" / "sample_tos.txt").read_text(encoding="utf-8")
logger = logging.getLogger("legallens.webapp")

app = FastAPI(title="LegalLens")
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=_HERE / "templates")


class InputError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Analysis:
    source: str
    text: str
    clauses: list[Clause]
    risks: list[Assessment]  # one per clause, same order
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "text": self.text,
            "clauses": [{**c.to_dict(), "risk": r.to_dict()} for c, r in zip(self.clauses, self.risks)],
            "warnings": self.warnings,
        }


@app.middleware("http")
async def size_limit(request: Request, call_next):
    """Reject oversized uploads before the body is read or parsed."""
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse({"detail": "Content-Length header is required."}, status_code=411)
        if not length.isdigit() or int(length) > _MAX_REQUEST_BYTES:
            return _error(request, f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    return templates.TemplateResponse(request, "index.html", _index_context())


@app.post("/analyze", response_class=HTMLResponse)
def analyze_page(
    request: Request, file: UploadFile | None = File(None), text: str = Form("")
) -> Response:
    try:
        analysis = _analyze(file, text)
    except InputError as exc:
        return _error(request, exc.message, exc.status_code)
    cards = _cards(analysis)
    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "analysis": analysis,
            "cards": cards,
            "print_groups": [(t, [c for c in cards if c["risk"].tier == t]) for t in TIERS],
            "generated_on": f"{date.today():%d %B %Y}".lstrip("0"),
            "summary": _risk_summary(analysis.risks),
            "spans": _spans(analysis.text, analysis.clauses, analysis.risks),
            "tier_labels": TIER_LABELS,
            "long_clause_chars": LONG_CLAUSE_CHARS,
            "result": analysis.to_dict(),
        },
    )


@app.post("/api/segment")
def analyze_api(file: UploadFile | None = File(None), text: str = Form("")) -> dict:
    try:
        return _analyze(file, text).to_dict()
    except InputError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _analyze(file: UploadFile | None, pasted: str) -> Analysis:
    started = time.perf_counter()
    has_file = file is not None and bool(file.filename)
    if has_file == bool(pasted.strip()):
        raise InputError("Upload one file or paste text, not both or neither.")

    if has_file:
        source = file.filename
        suffix = Path(source).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise InputError(f"Unsupported file type. Upload a {', '.join(ALLOWED_SUFFIXES)} file.")
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise InputError(f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
        if suffix == ".pdf":
            _check_pdf(data)
        try:
            text = load_bytes(data, suffix)
        except Exception as exc:  # pypdf raises many error types on malformed files
            logger.info("unreadable upload: %s", type(exc).__name__)
            raise InputError("This PDF could not be read. It may be damaged or encrypted.") from exc
        size = len(data)
    else:
        source = "Pasted text"
        text = normalize_text(pasted)
        size = len(pasted)

    clauses = segment(text)
    risks = [assess(c.text) for c in clauses]
    logger.info(
        "analyzed %s bytes into %d clauses in %.2fs", size, len(clauses), time.perf_counter() - started
    )
    return Analysis(source, text, clauses, risks, _warnings(text, clauses))


def _check_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        raise InputError("This file has a .pdf name but is not a PDF.")
    from pypdf import PdfReader

    try:
        pages = len(PdfReader(BytesIO(data)).pages)
    except Exception as exc:
        raise InputError("This PDF could not be read. It may be damaged or encrypted.") from exc
    if pages > MAX_PAGES:
        raise InputError(f"This PDF has {pages} pages; the limit is {MAX_PAGES}.", 413)


def _warnings(text: str, clauses: list[Clause]) -> list[str]:
    """Document-specific notes on where the segmentation is likely to be weak."""
    if not text.strip():
        return [
            "No text could be extracted. This may be a scanned PDF; "
            "text recognition (OCR) is not supported yet."
        ]
    warnings = []
    if "�" in text:
        warnings.append("Some characters could not be read from this PDF and are shown as �.")
    headed = [c for c in clauses if c.heading]
    if len(headed) >= 3 and not any(c.number for c in clauses):
        warnings.append(
            "No section numbers were found. If the document has numbered sections, "
            "its PDF font may hide the numbers; headings are shown without them."
        )
    long_count = sum(len(c.text) > LONG_CLAUSE_CHARS for c in clauses)
    if long_count:
        warnings.append(
            f"{long_count} clause(s) are longer than {LONG_CLAUSE_CHARS} characters and may "
            "contain several clauses merged together. They are marked below."
        )
    if headed:
        heading, count = Counter(c.heading for c in headed).most_common(1)[0]
        if count >= _CARRIED_HEADING_MIN_CLAUSES and count >= _CARRIED_HEADING_SHARE * len(clauses):
            warnings.append(
                f'The heading "{heading}" is attached to {count} clauses. It may be the '
                "document title rather than a section heading."
            )
    return warnings


def _spans(text: str, clauses: list[Clause], risks: list[Assessment]) -> list[dict]:
    """Split the text into clause spans and the gaps between them, in order."""
    spans = []
    pos = 0
    for clause in sorted(clauses, key=lambda c: c.start):
        if clause.start > pos:
            spans.append({"clause": None, "text": text[pos : clause.start]})
        spans.append(
            {"clause": clause.index, "tier": risks[clause.index].tier, "text": text[clause.start : clause.end]}
        )
        pos = clause.end
    if pos < len(text):
        spans.append({"clause": None, "text": text[pos:]})
    return spans


def _cards(analysis: Analysis) -> list[dict]:
    """Per-clause display data: the clause, its risk, and its text split around evidence."""
    cards = []
    for clause, risk in zip(analysis.clauses, analysis.risks):
        segments, pos = [], 0
        for e in risk.evidence:
            if e.start > pos:
                segments.append({"text": clause.text[pos : e.start], "hit": None})
            segments.append({"text": e.text, "hit": CATEGORY_BY_KEY[e.category].label})
            pos = e.end
        segments.append({"text": clause.text[pos:], "hit": None})
        phrases = {}
        for e in risk.evidence:  # first few distinct phrases per category, for "Why flagged"
            seen = phrases.setdefault(e.category, [])
            if e.text.lower() not in (p.lower() for p in seen) and len(seen) < 3:
                seen.append(e.text)
        cards.append(
            {
                "clause": clause,
                "risk": risk,
                "segments": segments,
                "categories": [(CATEGORY_BY_KEY[k], phrases[k]) for k in risk.categories],
            }
        )
    return cards


def _risk_summary(risks: list[Assessment]) -> dict:
    total = len(risks) or 1
    counts = Counter(r.tier for r in risks)
    tiers = [
        {"key": t, "count": counts[t], "percent": round(100 * counts[t] / total, 2)}
        for t in (*TIERS, "none")
    ]
    tally = Counter(k for r in risks for k in r.categories)
    categories = [(c, tally[c.key]) for c in CATEGORIES if tally[c.key]]
    return {"tiers": tiers, "categories": categories, "flagged": len(risks) - counts["none"]}


def _limits() -> dict:
    return {
        "max_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "max_pages": MAX_PAGES,
        "accept": ",".join(ALLOWED_SUFFIXES),
    }


def _index_context() -> dict:
    return {
        **_limits(),
        "sample_text": SAMPLE_TEXT,
        "tier_labels": TIER_LABELS,
        "categories_by_tier": [(t, [c for c in CATEGORIES if c.tier == t]) for t in TIERS],
        "category_count": len(CATEGORIES),
    }


def _error(request: Request, message: str, status_code: int) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=status_code)
    return templates.TemplateResponse(
        request, "index.html", {**_index_context(), "error": message}, status_code=status_code
    )
