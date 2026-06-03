"""Inspect extracted declaration JSONL files."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from roqet.schema import normalize_declaration


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [normalize_declaration(json.loads(line)) for line in fh if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path("data/declarations.jsonl"))
    parser.add_argument("--search")
    parser.add_argument("--lib")
    parser.add_argument("--kind")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    declarations = load(args.file)
    filtered = declarations
    if args.lib:
        filtered = [d for d in filtered if d["library"] == args.lib]
    if args.kind:
        filtered = [d for d in filtered if d["kind"].lower() == args.kind.lower()]
    if args.search:
        q = args.search.lower()
        filtered = [
            d
            for d in filtered
            if q in d["name"].lower()
            or q in d["type_signature"].lower()
            or q in d["docstring"].lower()
        ]

    print(f"Loaded {len(declarations)} declarations")
    print(f"Showing {min(args.limit, len(filtered))} of {len(filtered)} matches")
    print(f"With docstrings: {sum(1 for d in declarations if d['docstring'])}")
    print("Libraries:", dict(sorted(Counter(d["library"] for d in declarations).items())))
    print("Kinds:", dict(Counter(d["kind"] for d in declarations).most_common(10)))
    print()
    for d in filtered[: args.limit]:
        print(f"[{d['kind']:<12}] {d['name']}  ({d['library']})")
        print(f"  {d['type_signature'][:120]}")
        if d["github_url"]:
            print(f"  {d['github_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
