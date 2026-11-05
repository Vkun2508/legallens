"""Precision and recall of the compliance audit on the fixture policies.

    python scripts/eval_audit.py                 # keyword checker, free, no network
    python scripts/eval_audit.py --mode ai       # prints the estimated cost and stops
    python scripts/eval_audit.py --mode ai --yes # real Claude API calls (needs ANTHROPIC_API_KEY)
    python scripts/eval_audit.py --fixtures data/real_policies          # local-only real policies, see docs/evaluation.md

Violations are scored over (rule, clause) pairs on prohibited rules; --strict counts only
`non_compliant` verdicts (by default `unclear` counts as a flag too). Missing clauses are
scored over required rules whose status is not `pass`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legallens.compliance.audit import audit, has_ai_credentials  # noqa: E402
from legallens.compliance.evaluation import FIXTURE_DIR, Score, evaluate, load_fixtures, per_rule  # noqa: E402
from legallens.compliance.llm import LLMChecker, chunk_indices, estimate_cost, system_prompt  # noqa: E402
from legallens.compliance.rulebook import default_rulebook  # noqa: E402


def _pr(score: Score) -> str:
    return f"P {score.precision:5.2f}  R {score.recall:5.2f}  (tp {len(score.tp)}, fp {len(score.fp)}, fn {len(score.fn)})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("keyword", "ai"), default="keyword")
    parser.add_argument("--yes", action="store_true", help="confirm real API calls in --mode ai")
    parser.add_argument("--strict", action="store_true", help="count only non_compliant verdicts as violations")
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_DIR)
    args = parser.parse_args(argv)

    fixtures = load_fixtures(args.fixtures)
    rulebook = default_rulebook()
    checker = None
    if args.mode == "ai":
        if not has_ai_credentials():
            print("ANTHROPIC_API_KEY is not set; --mode ai needs it.", file=sys.stderr)
            return 2
        checker = LLMChecker()
        estimate = 0.0
        for f in fixtures:
            texts = [c.text for c in f.clauses]
            prompt = system_prompt(rulebook.checkable(f.business_type), rulebook.version)
            estimate += estimate_cost(checker.model, prompt, texts, chunk_indices(texts)) or 0.0
        print(f"{len(fixtures)} fixtures with {checker.model} (effort {checker.effort}): "
              f"estimated at most ${estimate:.2f}.")
        if not args.yes:
            print("Re-run with --yes to make the API calls.")
            return 1

    total_violations, total_missing, cost = Score(), Score(), 0.0
    print(f"\nRulebook {rulebook.version}, mode {args.mode}{' (strict)' if args.strict else ''}\n")
    for f in fixtures:
        report = audit(f.text, f.clauses, business_type=f.business_type,
                       mode="keyword" if args.mode == "keyword" else "auto", llm_checker=checker)
        if args.mode == "ai" and report.mode != "full":
            print(f"  ! {f.name}: AI check failed ({report.mode_reason}); keyword fallback was scored")
        cost += report.usage.get("cost_usd") or 0.0
        violations, missing = evaluate(report, f, strict=args.strict)
        total_violations.add(violations, f.name)
        total_missing.add(missing, f.name)
        print(f"{f.name:<24} score {report.score['value']:>3}")
        print(f"  violations  {_pr(violations)}")
        print(f"  missing     {_pr(missing)}")

    print("\nMicro-averaged over all fixtures")
    print(f"  violations  {_pr(total_violations)}")
    print(f"  missing     {_pr(total_missing)}")
    for title, score in (("violations", total_violations), ("missing", total_missing)):
        errors = {rule: c for rule, c in per_rule(score).items() if c["fp"] or c["fn"]}
        if errors:
            print(f"\nRules with {title} errors")
            for rule, c in errors.items():
                print(f"  {rule:<40} tp {c['tp']}  fp {c['fp']}  fn {c['fn']}")
    if args.mode == "ai":
        print(f"\nActual API cost: ${cost:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
