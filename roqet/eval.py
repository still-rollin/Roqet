"""Evaluate retrieval quality on the premise-selection benchmark.

Given each mined (statement -> premises) pair, query the *actual* search pipeline
with the statement and measure how well the premises are retrieved:
recall@k, MRR, and MAP. This runs the same retrieval + rerank path the API uses,
so config changes (ROQET_EMBEDDER / ROQET_SEARCH / ROQET_RERANK) are measured
directly.

    ROQET_EMBEDDER=fastembed python -m roqet.eval --limit 600

Compare configs by re-running with different env, e.g.:
    ROQET_SEARCH=fusion python -m roqet.eval --limit 600
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Default to the production embedder unless overridden.
os.environ.setdefault("ROQET_EMBEDDER", "fastembed")


def _retrieval():
    """Import the live pipeline lazily so env vars are read correctly."""
    from roqet import api, rerank

    def search(query: str, lib: str | None, k: int) -> list[str]:
        vector = api.embedder().embed([query])[0]
        hits = api.query_points(
            query=query,
            vector=vector,
            query_filter=api.build_filter(lib, None),
            limit=max(k, 50),
        )
        scored = rerank.rerank(query, hits, max(k, 50))
        return [(h.payload or {}).get("name", "") for h, _ in scored]

    return search


def average_precision(ranked: list[str], gold: set[str], k: int) -> float:
    hits = 0
    total = 0.0
    for i, name in enumerate(ranked[:k], start=1):
        if name in gold:
            hits += 1
            total += hits / i
    return total / min(len(gold), k) if gold else 0.0


def run_nl(args) -> int:
    """NL-query eval: query -> does the gold lemma (equivalence set) come back, and where?"""
    rows = [json.loads(line) for line in args.eval.open(encoding="utf-8") if line.strip()]
    search = _retrieval()
    k = args.k
    h1 = h5 = h10 = 0
    mrr = 0.0
    per_hint: dict[str, list[int]] = {}
    for r in rows:
        gold = set(r["gold"])
        names = search(r["query"], None, max(k, 20))  # global search, like a real user
        rank = next((i for i, n in enumerate(names, 1) if n in gold), None)
        if rank:
            h1 += rank <= 1; h5 += rank <= 5; h10 += rank <= 10
            mrr += 1.0 / rank
        per_hint.setdefault(r.get("hint", "?"), []).append(rank if rank and rank <= 10 else 0)
    n = max(len(rows), 1)
    print(f"\nNL-query eval  ({len(rows)} queries)   [embedder={os.environ.get('ROQET_EMBEDDER')} "
          f"search={os.environ.get('ROQET_SEARCH','dense')} rerank={os.environ.get('ROQET_RERANK','auto')}]")
    print("-" * 60)
    print(f"  hit@1  : {h1 / n:.3f}")
    print(f"  hit@5  : {h5 / n:.3f}")
    print(f"  hit@10 : {h10 / n:.3f}")
    print(f"  MRR@10 : {mrr / n:.3f}")
    print("  hit@10 by topic:")
    for hint, ranks in sorted(per_hint.items()):
        hits = sum(1 for x in ranks if x)
        print(f"    {hint:<10} {hits}/{len(ranks)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-type", choices=["premise", "nl"], default="premise")
    parser.add_argument("--eval", type=Path, default=Path("data/eval/premise_selection.jsonl"))
    parser.add_argument("--query-field", choices=["statement", "type_signature"], default="statement")
    parser.add_argument("--limit", type=int, default=600, help="Evenly-strided sample of pairs to score.")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--cross-lib", action="store_true",
                        help="Search the whole index (default restricts to the query's library).")
    args = parser.parse_args(argv)

    if args.eval_type == "nl":
        if args.eval == Path("data/eval/premise_selection.jsonl"):
            args.eval = Path("data/eval/nl_queries.jsonl")
        return run_nl(args)

    pairs = [json.loads(line) for line in args.eval.open(encoding="utf-8") if line.strip()]
    if len(pairs) > args.limit:
        step = len(pairs) / args.limit
        pairs = [pairs[int(i * step)] for i in range(args.limit)]

    search = _retrieval()
    k = args.k
    agg = {"r5": 0.0, "r10": 0.0, "mrr": 0.0, "map": 0.0}
    per_lib: dict[str, list[float]] = {}
    scored = 0

    for p in pairs:
        query = p.get(args.query_field) or p.get("statement") or ""
        gold = set(p["premises"])
        if not query.strip() or not gold:
            continue
        lib = None if args.cross_lib else p["library"]
        ranked = [n for n in search(query, lib, max(k, 50)) if n != p["name"]]

        r5 = len(set(ranked[:5]) & gold) / len(gold)
        r10 = len(set(ranked[:k]) & gold) / len(gold)
        mrr = next((1.0 / i for i, n in enumerate(ranked[:k], 1) if n in gold), 0.0)
        ap = average_precision(ranked, gold, k)

        agg["r5"] += r5; agg["r10"] += r10; agg["mrr"] += mrr; agg["map"] += ap
        per_lib.setdefault(p["library"], []).append(r10)
        scored += 1

    n = max(scored, 1)
    cfg = (f"embedder={os.environ.get('ROQET_EMBEDDER')} "
           f"search={os.environ.get('ROQET_SEARCH', 'dense')} "
           f"rerank={os.environ.get('ROQET_RERANK', 'auto')} "
           f"query={args.query_field} scope={'cross-lib' if args.cross_lib else 'same-lib'}")
    print(f"\nPremise-selection eval  ({scored} queries)   [{cfg}]")
    print("-" * 64)
    print(f"  recall@5  : {agg['r5'] / n:.3f}")
    print(f"  recall@10 : {agg['r10'] / n:.3f}")
    print(f"  MRR@10    : {agg['mrr'] / n:.3f}")
    print(f"  MAP@10    : {agg['map'] / n:.3f}")
    print("  recall@10 by library:")
    for lib, vals in sorted(per_lib.items()):
        print(f"    {lib:<10} {sum(vals) / len(vals):.3f}  ({len(vals)} q)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
