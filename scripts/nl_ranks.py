"""Per-query gold rank for the NL eval — see exactly where each gold lemma lands,
even when it's below the hit@10 threshold. Run against whatever store the API
points at (set QDRANT_URL/QDRANT_API_KEY for the cloud).

    ROQET_EMBEDDER=fastembed .venv/bin/python scripts/nl_ranks.py            # all
    ROQET_EMBEDDER=fastembed .venv/bin/python scripts/nl_ranks.py geocoq     # one topic
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ROQET_EMBEDDER", "fastembed")
from roqet import api, rerank  # noqa: E402

only = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].endswith(".jsonl") else None
path = next((a for a in sys.argv[1:] if a.endswith(".jsonl")), "data/eval/nl_queries.jsonl")
rows = [json.loads(l) for l in Path(path).open() if l.strip()]

DEPTH = 50
for r in rows:
    if only and r.get("hint") != only:
        continue
    gold = set(r["gold"])
    vec = api.embedder().embed([r["query"]])[0]
    hits = api.query_points(query=r["query"], vector=vec,
                            query_filter=api.build_filter(None, None), limit=DEPTH)
    names = [(h.payload or {}).get("name", "") for h, _ in rerank.rerank(r["query"], hits, DEPTH)]
    rank = next((i for i, n in enumerate(names, 1) if n in gold), None)
    pos = str(rank) if rank else f">{DEPTH}"
    print(f"[{r.get('hint','?'):<9}] rank={pos:<5} {r['query'][:60]}")
    print(f"            gold={sorted(gold)}  top3={names[:3]}")
