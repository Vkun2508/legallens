"""The action plan that goes with an audit: what to fix first, habits to keep, mistakes to avoid.

Guidance reads only report statuses, findings and the rulebook. Any checker that produces findings
per rule id (keyword, AI, or a trained model later) gets guidance unchanged. The wording lives in
`legallens/rulebook/guidance.yaml`; this module checks that file against the rulebook and turns a
report plus the user's review goal into the plan.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from legallens.compliance.report import AuditReport
from legallens.compliance.rulebook import RULEBOOK_DIR, SEVERITIES, Rulebook, default_rulebook

GOALS = ("prelaunch", "live", "quick")
DEFAULT_GOAL = "live"
QUICK_LIMIT = 5
QUICK_WATCH_LIMIT = 3
GROUP_KEYS = {
    "prelaunch": ("before_launch", "after_launch"),
    "live": ("now", "before_in_force", "next_update"),
    "quick": ("first",),
}
_ACTIONS = ("add", "reword", "check")
_STATUS_ACTION = {"missing": "add", "fail": "reword", "unclear": "check"}
_STATUS_ORDER = ("missing", "fail", "unclear")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GoalGroup(_Strict):
    key: str
    label: str


class Goal(_Strict):
    key: str
    label: str
    hint: str
    intro: str
    groups: list[GoalGroup]
    steps: list[str]


class Topic(_Strict):
    key: str
    title: str
    rules: list[str] = Field(min_length=1)
    manage: list[str] = Field(min_length=1)
    watch_out: list[str] = Field(min_length=1)


class Guidance(_Strict):
    version: str
    actions: dict[Literal["add", "reword", "check"], str]
    goals: list[Goal]
    topics: list[Topic]


def load_guidance(path: Path | str, rulebook: Rulebook) -> Guidance:
    guidance = Guidance(**yaml.safe_load(Path(path).read_text(encoding="utf-8")))
    if set(guidance.actions) != set(_ACTIONS):
        raise ValueError(f"actions must be exactly {', '.join(_ACTIONS)}")
    goal_keys = tuple(g.key for g in guidance.goals)
    if goal_keys != GOALS:
        raise ValueError(f"goals must be {GOALS} in that order, got {goal_keys}")
    for goal in guidance.goals:
        keys = tuple(g.key for g in goal.groups)
        if keys != GROUP_KEYS[goal.key]:
            raise ValueError(f"goal {goal.key!r}: groups must be {GROUP_KEYS[goal.key]} in that order, got {keys}")
    topic_keys = [t.key for t in guidance.topics]
    duplicates = sorted({k for k in topic_keys if topic_keys.count(k) > 1})
    if duplicates:
        raise ValueError(f"duplicate topic keys: {duplicates}")
    placed: dict[str, list[str]] = {}
    for topic in guidance.topics:
        for rule_id in topic.rules:
            placed.setdefault(rule_id, []).append(topic.key)
    unknown = sorted(set(placed) - set(rulebook.by_id))
    if unknown:
        raise ValueError(f"topics name rule ids the rulebook doesn't have: {unknown}")
    unplaced = [r.id for r in rulebook.rules if r.id not in placed]
    if unplaced:
        raise ValueError(f"rules in no topic: {unplaced}")
    repeated = {rule_id: keys for rule_id, keys in placed.items() if len(keys) > 1}
    if repeated:
        raise ValueError(f"rules in more than one topic: {repeated}")
    return guidance


@lru_cache(maxsize=1)
def default_guidance() -> Guidance:
    return load_guidance(RULEBOOK_DIR / "guidance.yaml", default_rulebook())


def _in_force(in_force_from: str | None, today: date) -> bool:
    return in_force_from is None or date.fromisoformat(in_force_from) <= today


def build_guidance(
    report: AuditReport, goal: str, today: date | None = None, guidance: Guidance | None = None
) -> dict:
    if goal not in GOALS:
        raise ValueError(f"goal must be one of {', '.join(GOALS)}")
    today = today or date.today()
    guidance = guidance or default_guidance()
    goal_cfg = next(g for g in guidance.goals if g.key == goal)
    topic_of = {rule_id: t.key for t in guidance.topics for rule_id in t.rules}
    topics = {t.key: t for t in guidance.topics}

    # Items: one per rule that needs action, most severe first, then missing before fail before unclear.
    clauses: dict[str, set[int]] = {}
    for f in report.findings:
        if f["verdict"] in ("non_compliant", "unclear"):
            clauses.setdefault(f["rule_id"], set()).add(f["clause_index"])
    items = []
    for rule in report.checkable:
        status = report.statuses[rule.id]
        if status not in _STATUS_ACTION:
            continue
        action = _STATUS_ACTION[status]
        items.append({
            **report._rule_ref(rule),
            "status": status,
            "action": action,
            "action_label": guidance.actions[action],
            "topic": topic_of[rule.id],
            "clause_indexes": sorted(clauses.get(rule.id, ())),
        })
    items.sort(key=lambda i: (SEVERITIES.index(i["severity"]), _STATUS_ORDER.index(i["status"])))

    # Which group each item belongs to, per goal.
    more = 0
    if goal == "quick":
        buckets = {"first": items[:QUICK_LIMIT]}
        more = max(0, len(items) - QUICK_LIMIT)
    elif goal == "prelaunch":
        buckets = {
            "before_launch": [i for i in items if i["severity"] != "minor"],
            "after_launch": [i for i in items if i["severity"] == "minor"],
        }
    else:
        def in_force(i):
            return _in_force(i["in_force_from"], today)

        buckets = {
            "now": [i for i in items if in_force(i) and i["severity"] != "minor"],
            "before_in_force": [i for i in items if not in_force(i)],
            "next_update": [i for i in items if in_force(i) and i["severity"] == "minor"],
        }
    groups = []
    for group in goal_cfg.groups:
        members = buckets[group.key]
        if not members:
            continue
        label = group.label
        if "{date}" in label:
            earliest = min(date.fromisoformat(i["in_force_from"]) for i in members if i["in_force_from"])
            label = label.format(date=f"{earliest:%d %B %Y}".lstrip("0"))
        groups.append({"key": group.key, "label": label, "items": members})

    shown = [i for group in groups for i in group["items"]]  # topics follow the order the plan shows
    touched = list(dict.fromkeys(i["topic"] for i in shown))
    entry = lambda key, points: {"topic": key, "title": topics[key].title, "points": points}  # noqa: E731

    if goal == "prelaunch":
        applicable = {topic_of[r.id] for r in report.rulebook.applicable(report.business_type)}
        order = touched + [t.key for t in guidance.topics if t.key in applicable and t.key not in touched]
        manage = [entry(k, topics[k].manage) for k in order]
    elif goal == "live":
        manage = [entry(k, topics[k].manage) for k in touched]
    else:
        manage = []
    if goal == "quick":
        watch_out = [entry(k, topics[k].watch_out[:1]) for k in touched[:QUICK_WATCH_LIMIT]]
    else:
        watch_out = [entry(k, topics[k].watch_out) for k in touched]

    return {
        "version": guidance.version,
        "goal": goal,
        "label": goal_cfg.label,
        "intro": goal_cfg.intro,
        "groups": groups,
        "manage": manage,
        "watch_out": watch_out,
        "steps": goal_cfg.steps,
        "more": more,
        "total": len(items),
    }
