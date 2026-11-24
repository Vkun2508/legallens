"""Shape an audit report for the pages: the annotated document, the missing clauses and the summary.

Rule severity reuses the reader's three colour slots (DESIGN.md "tiers"): critical sits in the
high (red) slot, major in medium (amber) and minor in low (grey). A clause takes the slot of its
most severe issue; a clause with no issues is "none". Every colour is shown next to its word.
"""

from __future__ import annotations

from collections import Counter

from legallens.compliance.report import AuditReport
from legallens.segmentation import Clause

SEVERITIES = ("critical", "major", "minor")
SEVERITY_TIER = {"critical": "high", "major": "medium", "minor": "low"}
TIERS = ("high", "medium", "low")
TIER_LABELS = {
    "high": ("Critical", "fix first"),
    "medium": ("Major", "fix soon"),
    "low": ("Minor", "worth fixing"),
    "none": ("No issues found", "nothing matched"),
}
VERDICT_LABELS = {"non_compliant": "Not met", "unclear": "Possible issue", "compliant": "Meets"}
BASIS_NOTES = {
    "best_practice": "Good practice: the law sets this duty, and saying so in your policy shows you meet it.",
}


def clause_ref(clause: Clause) -> str:
    return f"§ {clause.number}" if clause.number else f"Clause {clause.index + 1}"


def citation(rule: dict) -> str:
    """"DPDP Act s.6(4)", "E-Commerce Rules r.4(4)", "Dark Patterns Guidelines, Annex 1, item 5"."""
    section = rule["section"]
    joiner = " " if section[:2] in ("s.", "r.") else ", "
    return f"{rule['law_name']}{joiner}{section}"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _rule_view(rule: dict) -> dict:
    return {
        **rule,
        "citation": citation(rule),
        "tier": SEVERITY_TIER[rule["severity"]],
        "basis_note": BASIS_NOTES.get(rule["basis"]),
    }


def plan_view(guidance: dict, clauses: list[Clause], missing: list[dict] = ()) -> dict:
    """The action plan for the page, the one place clauses to add are listed.

    Each item gets its colour slot and citation. A clause to add carries its detail (`missing`, from
    `build_view`: what it means and the wording to fix it); a reword or check links to the first
    clause it is in. `rest` holds the clauses to add that a capped plan (the quick check-up) leaves
    out, so every missing clause still appears once; `more_issues` counts the left-out rewords and
    checks, which stay marked in the policy below.
    """
    by_index = {c.index: c for c in clauses}
    detail = {m["rule_id"]: m for m in missing}
    groups, shown = [], set()
    for group in guidance.get("groups", []):
        items = []
        for item in group["items"]:
            indexes = [i for i in item["clause_indexes"] if i in by_index]
            entry = {**_rule_view(item), "refs": [clause_ref(by_index[i]) for i in indexes]}
            if item["action"] == "add":
                found = detail.get(item["rule_id"], {})
                entry.update(href=None, what_it_means=found.get("what_it_means"), how_to_fix=found.get("how_to_fix"))
                shown.add(item["rule_id"])
            else:
                entry["href"] = f"#clause-{indexes[0]}" if indexes else None
            items.append(entry)
        groups.append({**group, "items": items})
    rest = [m for m in missing if m["rule_id"] not in shown]
    more_issues = max(0, guidance.get("more", 0) - len(rest))
    return {**guidance, "groups": groups, "rest": rest, "more_issues": more_issues}


def _segments(text: str, clause: Clause, issues: list[dict]) -> list[dict]:
    """The clause's span split around its issues' evidence, each match labelled with its rule."""
    spans = []
    for issue in issues:
        evidence = issue["evidence"]
        if not evidence:
            continue
        start, end = max(evidence["start"], clause.start), min(evidence["end"], clause.end)
        if start < end:
            spans.append((start, end, issue))
    kept: list[tuple] = []  # non-overlapping, preferring the earliest and then the longest
    for span in sorted(spans, key=lambda s: (s[0], -(s[1] - s[0]))):
        if kept and span[0] < kept[-1][1]:
            continue
        kept.append(span)
    segments, pos = [], clause.start
    for start, end, issue in kept:
        if start > pos:
            segments.append({"text": text[pos:start], "hit": None})
        segments.append({"text": text[start:end], "hit": issue["title"], "tier": issue["tier"]})
        pos = end
    if pos < clause.end:
        segments.append({"text": text[pos:clause.end], "hit": None})
    return segments


def build_view(text: str, clauses: list[Clause], report: AuditReport) -> dict:
    data = report.to_dict()
    rules = {r["rule_id"]: _rule_view(r) for r in data["rules"]}

    per_clause: dict[int, dict] = {c.index: {"issues": [], "covers": []} for c in clauses}
    for f in data["findings"]:
        rule = rules[f["rule_id"]]
        item = {
            **rule,
            "finding_id": f["id"],
            "verdict": f["verdict"],
            "verdict_label": VERDICT_LABELS[f["verdict"]],
            "explanation": f["explanation"],
            # A keyword match's explanation is generic, so show what the rule means instead;
            # an AI finding explains this clause specifically.
            "detail": f["explanation"] if f["source"] == "ai" else report.rulebook.by_id[f["rule_id"]].what_it_means,
            "evidence": f["evidence"],
            "matched": f["evidence"]["text"] if f["evidence"] else None,
            "wording": f["suggested_rewrite"] or f["how_to_fix"],
        }
        per_clause[f["clause_index"]]["covers" if f["verdict"] == "compliant" else "issues"].append(item)

    rows, pos = [], 0
    for clause in sorted(clauses, key=lambda c: c.start):
        gap = text[pos:clause.start].strip()
        if gap:
            rows.append({"kind": "gap", "text": gap})
        issues = sorted(per_clause[clause.index]["issues"], key=lambda i: SEVERITIES.index(i["severity"]))
        tier = issues[0]["tier"] if issues else "none"
        rows.append({
            "kind": "clause",
            "clause": clause,
            "ref": clause_ref(clause),
            "tier": tier,
            "issues": issues,
            "covers": per_clause[clause.index]["covers"],
            "segments": _segments(text, clause, issues),
            # One line for the homepage lens: what this clause may break, with the section.
            "note": "; ".join(f"{i['title']} ({i['citation']})" for i in issues),
        })
        pos = clause.end
    tail = text[pos:].strip()
    if tail:
        rows.append({"kind": "gap", "text": tail})

    clause_rows = [r for r in rows if r["kind"] == "clause"]
    tier_counts = Counter(r["tier"] for r in clause_rows)
    missing = [_rule_view(m) | {k: m[k] for k in ("what_it_means", "how_to_fix", "statute_quote")}
               for m in data["missing"]]
    issues = [(i, r) for r in clause_rows for i in r["issues"]]
    return {
        "data": data,
        "rows": rows,
        "missing": missing,
        "manual_checks": [_rule_view(m) | {"what_it_means": m["what_it_means"], "how_to_fix": m["how_to_fix"]}
                          for m in data["manual_checks"]],
        "tiers": [{"key": t, "count": tier_counts[t]} for t in (*TIERS, "none") if tier_counts[t]],
        "flagged": sum(tier_counts[t] for t in TIERS),
        "clause_count": len(clause_rows),
        "issue_count": len(issues),
        "print_groups": [
            (tier, [(i, r) for i, r in issues if i["tier"] == tier]) for tier in TIERS
        ],
        "status": status_sentences(data, len(issues), sum(tier_counts[t] for t in TIERS)),
    }


def status_sentences(data: dict, issue_count: int, flagged_clauses: int) -> list[str]:
    """Plain sentences for the header: rules met, what's missing, what to check, by severity."""
    counts = data["status_counts"]
    total = sum(counts.values())
    first = f"{counts['pass']} of {total} rules met."
    parts = []
    if counts["missing"]:
        parts.append(_plural(counts["missing"], "required clause") + (" is missing" if counts["missing"] == 1 else " are missing"))
    if counts["fail"]:
        parts.append(_plural(counts["fail"], "rule") + " not met")
    if issue_count:
        parts.append(f"{_plural(issue_count, 'possible issue')} to check in {_plural(flagged_clauses, 'clause')}")
    second = (_join(parts) + ".") if parts else "No possible issues were found."
    second = second[0].upper() + second[1:]
    by_severity = [f"{data['counts'][s]} {s}" for s in SEVERITIES if data["counts"][s]]
    lines = [first, second]
    if by_severity:
        lines.append(f"Missing or not met by severity: {_join(by_severity)}.")
    return lines
