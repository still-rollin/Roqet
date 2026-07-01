"""Generate a COMPLETELY INDEPENDENT NL eval set — no circularity with descriptions.

The paraphrase eval (make_query_eval.py) has a flaw: its queries are rewrites of the
same descriptions that are embedded in the docs, so query and doc share a common
ancestor. This script removes that: the query is generated from ONLY the lemma's
formal statement (Coq code). The LLM never sees the description (nor the identifier
name), so the query and the embedded description are two *independent* renderings of
the same lemma — matching them is genuine retrieval, not a summary matching its source.

Same 292 gold lemmas as the paraphrase eval, so the two are directly comparable:
"on identical lemmas, independent queries score X vs circular queries Y".

Input  : data/eval/nl_queries_mathcomp_q.jsonl   (gold names to reuse)
         data/declarations.mathcomp.ship.jsonl    (formal statements)
Output : data/eval/nl_queries_mathcomp_indep.jsonl  (query from statement, gold, hint)

    GEMINI_API_KEYS=key1,key2 python scripts/make_indep_eval.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import time
from pathlib import Path

import httpx

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"id": {"type": "INTEGER"}, "query": {"type": "STRING"}},
        "required": ["id", "query"],
    },
}

PROMPT_HEADER = (
    "You are generating evaluation queries for a semantic search engine over the "
    "Rocq/Coq MathComp library. For each item you are given ONLY the formal statement "
    "of a lemma or definition (Coq code) — no name, no description. Read the math and "
    "write ONE short search query a mathematician would type to find it.\n"
    "Rules:\n"
    "- Interpret what the statement asserts mathematically (unfold the notation).\n"
    "- 5 to 12 words, lowercase, no trailing period.\n"
    "- Capture the concept AND its relation/property (associative, injective, divides, "
    "a morphism, symmetric, ...), not just a noun.\n"
    "- Do NOT use Coq syntax, symbols, or any identifier names.\n"
    'Return a JSON array of {"id", "query"} for every item.\n\nStatements:\n'
)


def keys() -> list[str]:
    ks = [k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").split(",") if k.strip()]
    one = os.environ.get("GEMINI_API_KEY", "").strip()
    if one and one not in ks:
        ks.append(one)
    return ks


def gen_batch(batch: list[dict], key: str, timeout: float = 60.0) -> dict[int, str]:
    # Feed ONLY kind + statement/type — deliberately not the name or description.
    lines = []
    for i, b in enumerate(batch):
        body = (b.get("statement") or b.get("type_signature") or "")[:400]
        lines.append(f"[{i}] {b.get('kind','')} :: {body}")
    payload = {
        "contents": [{"parts": [{"text": PROMPT_HEADER + "\n".join(lines)}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    url = ENDPOINT.format(model=MODEL, key=key)
    for attempt in range(6):
        try:
            resp = httpx.post(url, json=payload, timeout=timeout)
        except httpx.RequestError:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return {int(it["id"]): str(it["query"]).strip()
                    for it in json.loads(text) if "id" in it}
        if resp.status_code in (403, 429, 500, 503):
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
    raise RuntimeError("Gemini retries exhausted")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--golds", type=Path, default=Path("data/eval/nl_queries_mathcomp_q.jsonl"))
    ap.add_argument("--corpus", type=Path, default=Path("data/declarations.mathcomp.ship.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("data/eval/nl_queries_mathcomp_indep.jsonl"))
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args(argv)

    ks = keys()
    if not ks:
        raise SystemExit("Set GEMINI_API_KEYS (comma-separated) or GEMINI_API_KEY.")
    key_cycle = itertools.cycle(ks)

    gold_rows = [json.loads(line) for line in args.golds.open(encoding="utf-8") if line.strip()]
    by_name = {d["name"]: d for d in
               (json.loads(line) for line in args.corpus.open(encoding="utf-8") if line.strip())}
    # attach each gold's formal statement (the ONLY thing the LLM will see)
    items = []
    for r in gold_rows:
        name = r["gold"][0]
        d = by_name.get(name)
        if d and (d.get("statement") or d.get("type_signature")):
            items.append({"gold": [name], "hint": r.get("hint", "?"),
                          "kind": d.get("kind", ""), "statement": d.get("statement", ""),
                          "type_signature": d.get("type_signature", "")})
    print(f"generating independent queries for {len(items)} lemmas ({len(ks)} key(s), model={MODEL})")

    out_rows = []
    for start in range(0, len(items), args.batch_size):
        batch = items[start:start + args.batch_size]
        got = gen_batch(batch, next(key_cycle))
        for i, b in enumerate(batch):
            q = got.get(i, "").strip()
            if not q or b["gold"][0].lower() in q.lower():   # safety: no identifier leak
                continue
            out_rows.append({"query": q, "gold": b["gold"], "hint": b["hint"],
                             "source_statement": (b["statement"] or b["type_signature"])[:200]})
        print(f"  {min(start + args.batch_size, len(items))}/{len(items)}")
        time.sleep(args.sleep)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_rows)} independent query/gold pairs -> {args.out}")
    if out_rows:
        print("\nexamples (independent query  <-  formal statement):")
        for r in out_rows[:5]:
            print(f"  Q: {r['query']}")
            print(f"     gold: {r['gold'][0]}  |  stmt: {r['source_statement'][:80]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
