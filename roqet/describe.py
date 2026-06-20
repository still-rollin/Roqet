"""Generate natural-language descriptions for declarations with Gemini.

Terse formal declarations (e.g. `mulrA`, GeoCoq `OFSC`) carry almost no text for a
semantic-search embedding to match an English query against. This makes a one-time,
OFFLINE pass that writes a plain-English `nl_description` per declaration; that text
is then embedded alongside the formal content. Serving stays LLM-free — this only
touches indexing.

Resumable: descriptions are cached by stable_id in data/descriptions_cache.jsonl,
so re-runs skip what's already done and a crash never loses work.

    GEMINI_API_KEY=... python -m roqet.describe --library geocoq
    GEMINI_API_KEY=... python -m roqet.describe --library geocoq --limit 24   # test slice

The API key is read from the environment and never written to disk.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx

from roqet.schema import normalize_declaration, stable_id

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"id": {"type": "INTEGER"}, "description": {"type": "STRING"}},
        "required": ["id", "description"],
    },
}

PROMPT_HEADER = (
    "You are writing search descriptions for declarations from a Rocq/Coq formal "
    "library, for a semantic search engine. For each declaration, write ONE concise "
    "plain-English sentence describing what it states or defines — the way a "
    "mathematician would phrase it when searching for it. Do NOT use Coq syntax and "
    "do NOT just restate the identifier name. Return a JSON array of "
    '{"id", "description"} for every item.\n\nDeclarations:\n'
)


def decl_line(i: int, d: dict) -> str:
    sig = d.get("type_signature") or ""
    stmt = (d.get("statement") or "")[:320]
    body = sig if sig else stmt
    return f"[{i}] {d.get('kind','')} {d.get('name','')} :: {body}"


def describe_batch(batch: list[dict], key: str, timeout: float = 60.0) -> dict[int, str]:
    prompt = PROMPT_HEADER + "\n".join(decl_line(i, d) for i, d in enumerate(batch))
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    url = ENDPOINT.format(model=MODEL, key=key)
    for attempt in range(6):
        try:
            resp = httpx.post(url, json=body, timeout=timeout)
        except httpx.RequestError:  # transient DNS/connection/timeout blip — back off and retry
            time.sleep(2 ** attempt * 2)
            continue
        if resp.status_code == 200:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            items = json.loads(text)
            return {int(it["id"]): str(it["description"]).strip() for it in items if "id" in it}
        if resp.status_code in (403, 429, 500, 503):  # 403 is intermittent on these tokens
            time.sleep(2 ** attempt * 2)
            continue
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
    raise RuntimeError("Gemini retries exhausted (rate limit / server errors)")


def load_cache(path: Path) -> dict[int, str]:
    cache: dict[int, str] = {}
    if path.exists():
        for line in path.open(encoding="utf-8"):
            if line.strip():
                rec = json.loads(line)
                cache[int(rec["id"])] = rec["nl_description"]
    return cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/declarations.enriched.jsonl"))
    parser.add_argument("--cache", type=Path, default=Path("data/descriptions_cache.jsonl"))
    parser.add_argument("--library", help="Only describe this library (e.g. geocoq). Default: all.")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0, help="Describe at most N (0 = all). For test runs.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Pause between calls (rate-limit friendly).")
    parser.add_argument("--write-back", action="store_true",
                        help="After describing, write nl_description into --input from the cache.")
    args = parser.parse_args(argv)

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("Set GEMINI_API_KEY in the environment.")

    records = [normalize_declaration(json.loads(l)) for l in args.input.open(encoding="utf-8") if l.strip()]
    cache = load_cache(args.cache)
    print(f"loaded {len(records):,} records; cache has {len(cache):,} descriptions")

    targets = [r for r in records if (not args.library or r["library"] == args.library)]
    todo = [r for r in targets if stable_id(r) not in cache]
    if args.limit:
        todo = todo[: args.limit]
    print(f"describing {len(todo):,} of {len(targets):,} '{args.library or 'all'}' declarations (rest cached)")

    args.cache.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    with args.cache.open("a", encoding="utf-8") as cf:
        failed = 0
        for start in range(0, len(todo), args.batch_size):
            batch = todo[start : start + args.batch_size]
            try:
                results = describe_batch(batch, key)
            except Exception as exc:  # noqa: BLE001 - one bad batch must not kill the run
                failed += len(batch)
                print(f"  [{done}/{len(todo)}] batch failed, skipping: {str(exc)[:100]}")
                time.sleep(args.sleep)
                continue
            for i, d in enumerate(batch):
                desc = results.get(i)
                if desc:
                    cf.write(json.dumps({"id": stable_id(d), "name": d["name"],
                                         "nl_description": desc}, ensure_ascii=False) + "\n")
                    cf.flush()
            done += len(batch)
            print(f"  [{done}/{len(todo)}] described")
            time.sleep(args.sleep)
        if failed:
            print(f"  {failed} declarations failed this pass — re-run to retry them (cache resumes the rest).")

    if args.write_back:
        cache = load_cache(args.cache)
        out = args.input.with_suffix(".tmp")
        updated = 0
        with out.open("w", encoding="utf-8") as f:
            for r in records:
                desc = cache.get(stable_id(r))
                if desc:
                    r["nl_description"] = desc
                    updated += 1
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        out.replace(args.input)
        print(f"wrote nl_description into {args.input} for {updated:,} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
