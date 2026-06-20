# Contributing to Rocqet

Thanks for your interest! Rocqet is semantic search over Rocq/Coq libraries.
This guide covers local setup and the conventions CI enforces.

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[local,dev]"      # embedder backend + pytest/ruff
cd web && npm install && cd ..      # frontend (only if touching the UI)
```

See the [README](README.md) for the dependency extras (`serve`, `local`,
`openai`, `mcp`, `dev`) and how to build/obtain the dataset
([docs/DATA.md](docs/DATA.md)).

## Before opening a PR

CI (`.github/workflows/ci.yml`) runs these — please run them locally first:

```bash
ruff check rocqet tests scripts    # lint (line length 100)
pytest -q                          # backend tests
cd web && npx tsc --noEmit         # frontend typecheck (if UI changed)
```

- Add or update tests for behavior changes. Prefer tests that need no network,
  Qdrant, or model download (see `tests/test_api.py` for the pattern).
- Keep changes focused; match the surrounding style.
- Serving must stay **LLM-free**. LLM use is fine offline/at index time only
  (e.g. `rocqet.describe`), never in the `/search` request path.

## Project conventions

- **Schema** is canonical in `rocqet/schema.py` — extend `normalize_declaration`
  rather than reading raw fields elsewhere.
- **Env vars** use the `ROCQET_` prefix.
- **Indexing is zero-downtime**: point ids are deterministic (`stable_id`), so
  re-indexing upserts in place. Never `--reset` a live remote collection; use
  `--prune` (see `scripts/index_cloud.sh`).
- **Data files** (`deploy/*.jsonl`, `data/`) are build artifacts — not committed.

## Reporting issues

Open a GitHub issue with the query, the expected vs. actual result, and the
library/version if relevant. Retrieval-quality reports are especially welcome —
include the query and which lemma you expected.
