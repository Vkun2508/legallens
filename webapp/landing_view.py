"""The homepage scan: the sample policy's real audit, shaped for the hero's scene.

The hero plays an audit of the bundled sample policy: its clauses on a sheet, the clauses with
possible issues lifting off with their citations, and three of the missing clauses opening as empty
slots after the clause they belong with. Everything here comes from the audit report; nothing is
invented for the page. The scene is server-rendered, so it also reads without JavaScript.
"""

from __future__ import annotations

import re
from collections import Counter

from markupsafe import Markup, escape

from legallens.compliance.report import AuditReport
from legallens.segmentation import Clause

FOCUS_RULE = "dpdp.consent.withdrawal_ease"
LAW_SHORT = {"dpdp": "DPDP Act", "dark_patterns": "Dark patterns", "ecommerce": "E-Commerce Rules"}

# Missing clauses the hero shows as slots, in order, with a short title and the heading words of the
# clause each belongs after. Only those the audit really reports as missing are shown.
SLOT_RULES = (
    ("dpdp.children.parental_consent", "Parental consent for under-18s", ("collect",)),
    ("dpdp.fiduciary.breach_intimation", "Telling users and the Board about a breach", ("security", "storage")),
    ("dpdp.notice.board_complaint", "How to complain to the Data Protection Board", ("contact", "grievance")),
)


def _citation(findings: list[dict]) -> str:
    """One label for a clause's possible issues: 'DPDP Act s.6(4)' or 'Dark patterns, Annex 1 items 12 and 5'."""
    cites = [(f["law"], f["section"]) for f in findings]
    if len(cites) > 1 and all(law == "dark_patterns" for law, _ in cites):
        items = [re.sub(r"^Annex 1, item ", "", section) for _, section in cites]
        return "Dark patterns, Annex 1 items " + " and ".join(items)
    return ", ".join(f"{LAW_SHORT.get(law, law)} {section}" for law, section in cites)


def _marked(text: str, start: int, end: int, spans: list[tuple[int, int]], tier: str) -> Markup:
    """The clause text, escaped, with each evidence span wrapped in a <mark>."""
    out, pos = [], start
    for s, e in spans:
        s, e = max(s, pos), min(e, end)
        if s >= e:
            continue
        out.append(escape(text[pos:s]))
        out.append(Markup('<mark class="{}">{}</mark>').format(tier, text[s:e]))
        pos = e
    out.append(escape(text[pos:end]))
    return Markup("").join(out)


def build_scan(text: str, clauses: list[Clause], report: AuditReport) -> dict:
    data = report.to_dict()
    by_clause: dict[int, list[dict]] = {}
    for f in data["findings"]:
        if f["verdict"] == "unclear" and f.get("evidence"):
            by_clause.setdefault(f["clause_index"], []).append(f)

    missing = {m["rule_id"]: m for m in data["missing"]}
    slots_after: dict[int, list[dict]] = {}
    for rule_id, title, words in SLOT_RULES:
        rule = missing.get(rule_id)
        if not rule:
            continue
        after = next((i for i, c in enumerate(clauses) if c.heading and any(w in c.heading.lower() for w in words)),
                     len(clauses) - 1)
        slots_after.setdefault(after, []).append({
            "kind": "slot", "title": title, "tier": rule["severity"], "rule_title": rule["title"],
            "cite": f"{rule['law_name']} {rule['section']}",
        })

    items = []
    for i, clause in enumerate(clauses):
        findings = by_clause.get(i, [])
        flag = None
        if findings:
            tier = "critical" if any(f["severity"] == "critical" for f in findings) else findings[0]["severity"]
            spans = []
            for f in sorted(findings, key=lambda f: f["evidence"]["start"]):
                s, e = f["evidence"]["start"], f["evidence"]["end"]
                if spans and s < spans[-1][1]:
                    spans[-1] = (spans[-1][0], max(spans[-1][1], e))
                else:
                    spans.append((s, e))
            flag = {"tier": tier, "cite": _citation(findings), "count": len(findings),
                    "title": findings[0]["title"] if len(findings) == 1 else " and ".join(f["title"] for f in findings),
                    "rule_ids": [f["rule_id"] for f in findings], "quote": findings[0]["evidence"]["text"]}
            body = _marked(text, clause.start, clause.end, spans, tier)
        else:
            body = escape(clause.text)
        items.append({"kind": "clause", "number": clause.number, "heading": clause.heading, "html": body, "flag": flag})
        items.extend(slots_after.get(i, []))

    # The read's two close-ups: the hard-to-withdraw consent clause (or the first critical flag), then
    # the first missing clause.
    flagged = [it for it in items if it["kind"] == "clause" and it["flag"]]
    focus_clause = next((it for it in flagged if FOCUS_RULE in it["flag"]["rule_ids"]),
                        next((it for it in flagged if it["flag"]["tier"] == "critical"), flagged[0] if flagged else None))
    focus_slot = next((it for it in items if it["kind"] == "slot"), None)
    for k, it in enumerate((focus_clause, focus_slot), start=1):
        if it is not None:
            it["focus"] = k

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "title": lines[0] if lines else "Sample policy",
        "updated": next((line for line in lines[1:4] if line.lower().startswith("last updated")), ""),
        "items": items,
        "focus_clause": focus_clause,
        "focus_slot": focus_slot,
        "clauses": len(clauses),
        "score": data["score"]["value"],
        "issues": data["status_counts"]["unclear"],
        "missing": data["status_counts"]["missing"],
        "rulebook": data["rulebook_version"],
        # When most DPDP duties apply: the in-force date most of the DPDP rules carry.
        "in_force": Counter(r["in_force_from"] for r in data["rules"] if r["law"] == "dpdp" and r.get("in_force_from")).most_common(1)[0][0],
    }
