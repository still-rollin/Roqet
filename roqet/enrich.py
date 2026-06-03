"""Rule-based declaration enrichment and deduplication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from roqet.schema import canonical_key, normalize_declaration


class RuleBasedEnricher:
    def describe(self, declaration: dict) -> str:
        d = normalize_declaration(declaration)
        signature = d["type_signature"] or d["statement"]
        if signature:
            return f"{d['kind']} {d['name']}: {signature}"
        if d["kind"] in {"Inductive", "CoInductive"}:
            return f"Defines the inductive type {d['name']}."
        if d["kind"] in {"Definition", "Fixpoint", "CoFixpoint"}:
            return f"Defines {d['name']}."
        return f"{d['kind']} {d['name']} from {d['library']}."


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path: Path, declarations: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for declaration in declarations:
            fh.write(json.dumps(declaration, ensure_ascii=False) + "\n")


def enrich_declarations(declarations: list[dict], enricher: RuleBasedEnricher | None = None) -> list[dict]:
    enricher = enricher or RuleBasedEnricher()
    enriched = []
    for raw in declarations:
        d = normalize_declaration(raw)
        if not d["docstring"]:
            d["docstring"] = enricher.describe(d)
            d["docstring_generated"] = True
        else:
            d["docstring_generated"] = False
        enriched.append(d)
    return enriched


def deduplicate_cross_library(declarations: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for raw in declarations:
        d = normalize_declaration(raw)
        semantic_key = f"{d['library']}:{d['kind']}:{d['name']}:{d['type_signature']}"
        if semantic_key in seen:
            continue
        seen.add(semantic_key)
        out.append(d)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/declarations.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/declarations.enriched.jsonl"))
    parser.add_argument("--dedupe", action="store_true")
    args = parser.parse_args(argv)

    declarations = enrich_declarations(load_jsonl(args.input))
    if args.dedupe:
        declarations = deduplicate_cross_library(declarations)
    write_jsonl(args.out, declarations)
    print(f"Wrote {len(declarations)} declarations to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
