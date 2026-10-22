"""Command-line entry point: python -m legallens segment FILE [--json]."""

from __future__ import annotations

import argparse
import json
import sys

from legallens.preprocess import load_document
from legallens.segmentation import segment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m legallens")
    sub = parser.add_subparsers(dest="command", required=True)
    seg = sub.add_parser("segment", help="split an agreement into clauses")
    seg.add_argument("file", help=".txt, .md or text-based .pdf file")
    seg.add_argument("--json", action="store_true", help="print clauses as JSON")
    args = parser.parse_args(argv)

    clauses = segment(load_document(args.file))
    if args.json:
        json.dump([c.to_dict() for c in clauses], sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    for c in clauses:
        label = " | ".join(part for part in (c.number, c.heading) if part) or "-"
        print(f"[{c.index}] {label}")
        print(f"    {c.text.replace(chr(10), chr(10) + '    ')}\n")
    print(f"{len(clauses)} clauses", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
