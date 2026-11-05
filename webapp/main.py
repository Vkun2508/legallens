"""LegalLens web app: audit a privacy policy or terms against Indian law.

Run locally with:  uvicorn webapp.main:app
(uvicorn listens on 127.0.0.1 by default; uploads may be unpublished policies, so
exposing it more widely is a separate decision.)

Uploads are processed in memory and discarded after the response: nothing is
written to disk or kept, and logs record sizes and counts, never content.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Callable
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exception_handlers import http_exception_handler
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartParser

from legallens import Assessment, Clause, assess, load_bytes, normalize_text, segment
from legallens.compliance.audit import PARTIAL_REASONS, AuditInputError
from legallens.compliance.audit import audit as run_audit
from legallens.compliance.llm import LLMChecker
from legallens.compliance.report import AuditReport
from legallens.compliance.rulebook import default_rulebook
from legallens.webpage import FetchedPolicy, FetchError, display_url, fetch_policy
from webapp.audit_view import TIER_LABELS, build_view, citation
from webapp.landing_view import build_scan

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PAGES = 200
ALLOWED_SUFFIXES = (".pdf", ".txt", ".md")
LONG_CLAUSE_CHARS = 1500
BUSINESS_TYPES = (
    ("app", "App or website", "DPDP Act and dark patterns"),
    ("ecommerce", "Online store", "Adds the E-Commerce Rules"),
    ("marketplace", "Marketplace", "Adds the rules on seller information"),
)
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
SAMPLE_TEXT = (_HERE.parent / "data" / "samples" / "sample_privacy_policy.txt").read_text(encoding="utf-8")
logger = logging.getLogger("legallens.webapp")

app = FastAPI(title="LegalLens")
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=_HERE / "templates")

# A line break that is structure, not wrapping: before a blank line or a sub-item like "(a)" or "•".
_HARD_BREAK_RE = re.compile(r"\n(?=\n|\s*(?:\(?[a-z0-9]{1,4}\)|[•·*\-]\s))")


def _doc_breaks(text: str) -> Markup:
    """Escape document text and mark its structural line breaks with <br>.

    Wrapped lines then flow as one paragraph in the browser, while the text itself
    (newlines included) stays exactly as extracted.
    """
    return Markup(_HARD_BREAK_RE.sub("\n<br>", str(escape(text))))


templates.env.filters["doc_breaks"] = _doc_breaks


def get_llm_checker() -> LLMChecker | None:
    """The AI checker for audits; None means the default (used only when an API key is set)."""
    return None


def get_url_fetcher() -> Callable[[str], FetchedPolicy]:
    """Fetches a policy from a web address (tests replace it, so pytest never touches the network)."""
    return fetch_policy


class InputError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Analysis:
    """Clause segmentation with v1's keyword risk tags: the /api/segment response."""

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


@dataclass
class AuditResult:
    source: str
    text: str
    clauses: list[Clause]
    report: AuditReport
    warnings: list[str]
    generated_at: str

    def to_dict(self) -> dict:
        """The /api/audit response, also embedded in the results page for export."""
        return {
            "source": self.source,
            "generated_at": self.generated_at,
            **self.report.to_dict(),
            "warnings": self.warnings,
            "clauses": [c.to_dict() for c in self.clauses],
            "text": self.text,
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


@app.post("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request,
    file: UploadFile | None = File(None),
    text: str = Form(""),
    business_type: str = Form("app"),
    name: str = Form(""),
    url: str = Form(""),
    llm_checker: LLMChecker | None = Depends(get_llm_checker),
    fetcher: Callable[[str], FetchedPolicy] = Depends(get_url_fetcher),
) -> Response:
    try:
        result = _audit(file, text, business_type, "auto", llm_checker, name=name, url=url, fetcher=fetcher)
    except InputError as exc:
        form = {"text": text, "business_type": business_type, "url": url}
        return _error(request, exc.message, exc.status_code, form=form)
    return templates.TemplateResponse(
        request,
        "audit.html",
        {
            "result": result,
            "view": build_view(result.text, result.clauses, result.report),
            "tier_labels": TIER_LABELS,
            "generated_on": f"{date.today():%d %B %Y}".lstrip("0"),
            "long_clause_chars": LONG_CLAUSE_CHARS,
            "result_data": result.to_dict(),
        },
    )


@app.post("/api/segment")
def analyze_api(file: UploadFile | None = File(None), text: str = Form("")) -> dict:
    try:
        return _analyze(file, text).to_dict()
    except InputError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@app.post("/api/audit")
def audit_api(
    file: UploadFile | None = File(None),
    text: str = Form(""),
    business_type: str = Form("app"),
    mode: str = Form("auto"),
    llm_checker: LLMChecker | None = Depends(get_llm_checker),
) -> dict:
    """Compliance audit: score, findings with citations, missing clauses and manual checks."""
    try:
        return _audit(file, text, business_type, mode, llm_checker).to_dict()
    except InputError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


@app.post("/api/audit-url")
def audit_url_api(
    url: str = Form(""),
    business_type: str = Form("app"),
    mode: str = Form("auto"),
    llm_checker: LLMChecker | None = Depends(get_llm_checker),
    fetcher: Callable[[str], FetchedPolicy] = Depends(get_url_fetcher),
) -> dict:
    """The same audit as /api/audit, for a policy the server fetches from a web address."""
    if not url.strip():
        raise HTTPException(400, "Enter the web address of your privacy policy or terms.")
    try:
        return _audit(None, "", business_type, mode, llm_checker, url=url, fetcher=fetcher).to_dict()
    except InputError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _audit(file: UploadFile | None, pasted: str, business_type: str, mode: str,
           llm_checker: LLMChecker | None, name: str = "", url: str = "",
           fetcher: Callable[[str], FetchedPolicy] | None = None) -> AuditResult:
    started = time.perf_counter()
    notes: list[str] = []
    if url.strip():
        if (file is not None and file.filename) or pasted.strip():
            raise InputError("Give a web address, a file or pasted text, one at a time.")
        source, doc_text, size, notes = _read_url(url, fetcher or fetch_policy)
    else:
        source, doc_text, size = _read_input(file, pasted)
    if name.strip() and source == "Pasted text":
        source = name.strip()[:120]  # a label for pasted text, e.g. the homepage sample
    if not doc_text.strip():
        raise InputError("No text could be extracted. This may be a scanned PDF; paste the text instead.", 422)
    clauses = segment(doc_text)
    try:
        report = run_audit(doc_text, clauses, business_type=business_type, mode=mode, llm_checker=llm_checker)
    except AuditInputError as exc:
        raise InputError(str(exc), exc.status_code) from exc
    warnings = notes + _warnings(doc_text, clauses)
    if report.mode_reason:
        warnings.insert(0, PARTIAL_REASONS.get(report.mode_reason, "This is a keyword check only."))
    logger.info(
        "audited %s bytes, %d clauses, mode=%s reason=%s in %.2fs",
        size, len(clauses), report.mode, report.mode_reason, time.perf_counter() - started,
    )
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return AuditResult(source, doc_text, clauses, report, warnings, generated_at)


def _analyze(file: UploadFile | None, pasted: str) -> Analysis:
    started = time.perf_counter()
    source, text, size = _read_input(file, pasted)
    clauses = segment(text)
    analysis = Analysis(source, text, clauses, [assess(c.text) for c in clauses], _warnings(text, clauses))
    logger.info(
        "analyzed %s bytes into %d clauses in %.2fs", size, len(clauses), time.perf_counter() - started
    )
    return analysis


def _read_input(file: UploadFile | None, pasted: str) -> tuple[str, str, int]:
    """Validate the upload or pasted text and return (source name, normalized text, size in bytes)."""
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
    return source, text, size


def _read_url(url: str, fetcher: Callable[[str], FetchedPolicy]) -> tuple[str, str, int, list[str]]:
    """Fetch a policy from the web and return (source label, normalized text, size, notes)."""
    try:
        fetched = fetcher(url)
    except FetchError as exc:
        raise InputError(exc.message, exc.status_code) from exc
    if fetched.kind == "pdf":
        _check_pdf(fetched.body)
        try:
            text = load_bytes(fetched.body, ".pdf")
        except Exception as exc:  # pypdf raises many error types on malformed files
            raise InputError("This PDF could not be read. It may be damaged or encrypted.") from exc
        size = len(fetched.body)
    else:
        text, size = fetched.text, len(fetched.text)
    notes = []
    if fetched.found_from:
        notes.append(
            f"LegalLens followed the policy link on {display_url(fetched.found_from) or fetched.found_from} "
            f"to {display_url(fetched.url)}. If that isn't the right document, link to it directly."
        )
    return display_url(fetched.url) or "Web page", text, size, notes


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


def _limits() -> dict:
    return {
        "max_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "max_pages": MAX_PAGES,
        "accept": ",".join(ALLOWED_SUFFIXES),
    }


def _sample_view() -> dict:
    """The bundled sample policy, audited once: the homepage scan and the worked example read it."""
    text = normalize_text(SAMPLE_TEXT)
    clauses = segment(text)
    report = run_audit(text, clauses, mode="keyword")
    view = build_view(text, clauses, report)
    clause_rows = [r for r in view["rows"] if r["kind"] == "clause"]
    # The worked example and the lens's resting place: the hard-to-withdraw consent clause,
    # a critical issue every founder can picture fixing.
    example = next(
        (r for r in clause_rows if any(i["rule_id"] == "dpdp.consent.withdrawal_ease" for i in r["issues"])),
        next((r for r in clause_rows if r["tier"] == "high"), None),
    )
    # The draft-fixes excerpt on the homepage: the free trial that turns paid without notice.
    fixes = next((r for r in clause_rows if any(i["rule_id"] == "dark.saas_billing" for i in r["issues"])), None)
    return {"rows": view["rows"], "example": example, "fixes": fixes, "view": view,
            "scan": build_scan(text, clauses, report)}


def _law_table() -> list[dict]:
    rulebook = default_rulebook()
    rows = []
    for law in rulebook.laws:
        rules = [r for r in rulebook.rules if r.law == law.key]
        rows.append({
            "name": law.name,
            "summary": law.summary,
            "checked": sum(r.scope == "text" for r in rules),
            "manual": sum(r.scope == "ui" for r in rules),
            "applies": "All businesses" if any(r.applies_to == "all" for r in rules) else "Online stores and marketplaces",
        })
    return rows


def _rule_card(rule_id: str = "dpdp.children.parental_consent") -> dict:
    """One rule as the rulebook holds it, for the homepage: the rule Kettle's sample is missing
    and the one the US-style "under 13" templates fail."""
    rulebook = default_rulebook()
    rule = next(r for r in rulebook.rules if r.id == rule_id)
    law = next(l for l in rulebook.laws if l.key == rule.law)
    return {
        "id": rule.id,
        "title": rule.title,
        "severity": rule.severity,
        "citation": citation({"law_name": law.short_name, "section": rule.section}),
        "also_cites": rule.also_cites,
        "what_it_means": rule.what_it_means,
        "how_to_fix": rule.how_to_fix,
        "quote": rule.source.quote,
        "verified": rule.source.verified,
    }


def _index_context() -> dict:
    in_force = date.fromisoformat(SAMPLE_VIEW["scan"]["in_force"])
    return {
        **_limits(),
        "in_force": in_force,
        "in_force_label": f"{in_force:%d %B %Y}".lstrip("0"),
        "days_to_in_force": max(0, (in_force - date.today()).days),
        "sample": SAMPLE_VIEW,
        "sample_text": SAMPLE_TEXT,
        "tier_labels": TIER_LABELS,
        "laws": LAW_TABLE,
        "rule_card": RULE_CARD,
        "business_types": BUSINESS_TYPES,
        "rulebook_version": default_rulebook().version,
    }


SAMPLE_VIEW = _sample_view()
LAW_TABLE = _law_table()
RULE_CARD = _rule_card()


def _error(request: Request, message: str, status_code: int, form: dict | None = None) -> Response:
    """JSON for the API; for the web form, the homepage again with the message beside the form that
    was used (the address box in the hero, or the upload form) and what the visitor entered kept."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=status_code)
    form = form or {}
    origin = "url" if form.get("url", "").strip() else "upload"
    context = {**_index_context(), "error": message, "error_origin": origin, "form": form}
    return templates.TemplateResponse(request, "index.html", context, status_code=status_code)


@app.exception_handler(StarletteHTTPException)
async def not_found(request: Request, exc: StarletteHTTPException) -> Response:
    """A page in the site's own look for unknown addresses; the API keeps its JSON errors."""
    if exc.status_code != 404 or request.url.path.startswith("/api/"):
        return await http_exception_handler(request, exc)
    return templates.TemplateResponse(request, "404.html", {}, status_code=404)
