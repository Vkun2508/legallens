"""Run a compliance audit: choose a checker, fall back when the AI check fails, build the report.

    auto mode, API key set     -> AI checker      -> report mode "full"
    no key, keyword requested,
    or any AI failure          -> keyword checker -> report mode "partial" (with mode_reason)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence

from legallens.compliance.keyword import KeywordChecker
from legallens.compliance.llm import LLMChecker, LLMCheckError
from legallens.compliance.report import AuditReport, build_report
from legallens.compliance.rulebook import Rulebook, default_rulebook
from legallens.compliance.unfair_terms import check_document
from legallens.segmentation import Clause

logger = logging.getLogger("legallens.compliance")

MAX_AUDIT_CHARS = 150_000
MODES = ("auto", "keyword")

PARTIAL_REASONS = {
    "keyword_requested": "Keyword check only, as requested.",
    "no_api_key": "This is a keyword check of the wording against the rulebook, not a legal review.",
    "cost_cap": "This document is too long for an AI review within the cost limit, so this is a keyword check only.",
    "llm_refusal": "The AI review declined this document, so this is a keyword check only.",
    "llm_invalid_output": "The AI review returned an unusable answer, so this is a keyword check only.",
    "api_auth_error": "The AI service rejected our credentials, so this is a keyword check only.",
    "api_rate_limited": "The AI service is busy, so this is a keyword check only. Try again in a few minutes.",
    "api_error": "The AI service returned an error, so this is a keyword check only.",
    "api_unreachable": "The AI service could not be reached, so this is a keyword check only.",
}


class AuditInputError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def has_ai_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _with_unfair_terms(report: AuditReport, text: str, clauses: Sequence[Clause], enabled: bool) -> AuditReport:
    if enabled:
        report.unfair_terms = check_document(text, clauses)
    return report


def audit(
    text: str,
    clauses: Sequence[Clause],
    *,
    business_type: str = "app",
    mode: str = "auto",
    rulebook: Rulebook | None = None,
    llm_checker: LLMChecker | None = None,
    unfair_terms: bool = False,
) -> AuditReport:
    """Audit segmented document text. `llm_checker` overrides the default AI checker (tests inject one).

    `unfair_terms=True` adds the bundled unfair-terms model's flags as `report.unfair_terms` (never scored).
    """
    if mode not in MODES:
        raise AuditInputError(f"mode must be one of {', '.join(MODES)}")
    if len(text) > MAX_AUDIT_CHARS:
        raise AuditInputError(f"The document is longer than {MAX_AUDIT_CHARS:,} characters.", 413)
    rulebook = rulebook or default_rulebook()
    try:
        rules = rulebook.checkable(business_type)
    except ValueError as exc:
        raise AuditInputError(str(exc)) from exc
    clause_texts = [c.text for c in clauses]
    common = {"rulebook": rulebook, "business_type": business_type}

    if mode == "keyword":
        reason = "keyword_requested"
    elif llm_checker is None and not has_ai_credentials():
        reason = "no_api_key"
    else:
        checker = llm_checker or LLMChecker()
        try:
            result = checker.check(clause_texts, rules, rulebook.version)
        except LLMCheckError as exc:
            reason = exc.reason
            logger.warning("AI check failed (%s); using keyword fallback", exc.reason)
        else:
            report = build_report(text, clauses, result.findings, mode="full", model=checker.model,
                                  usage=result.usage.to_dict(checker.model), **common)
            return _with_unfair_terms(report, text, clauses, unfair_terms)

    findings = KeywordChecker().check(clause_texts, rules)
    report = build_report(text, clauses, findings, mode="partial", mode_reason=reason, **common)
    return _with_unfair_terms(report, text, clauses, unfair_terms)
