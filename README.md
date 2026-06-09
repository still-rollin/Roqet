# Roqet

**Semantic search over Rocq/Coq mathematical libraries.**

Roqet lets you find theorems, lemmas, and definitions across large Rocq/Coq
libraries by describing what you want in plain language — no need to remember the
exact name. It extracts declarations from `.v` files, enriches sparse metadata,
embeds them into a [Qdrant](https://qdrant.tech) vector index, serves search
through a FastAPI backend, and presents results in a Next.js UI.

```
  .v files ──▶ extract ──▶ enrich ──▶ embed ──▶ Qdrant ──▶ FastAPI ──▶ Next.js UI
              (Phase 1)   (Phase 4)  (Phase 2)  (index)    (Phase 3)
```

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Setup](#setup)
- [Quick start (offline demo)](#quick-start-offline-demo)
- [Full pipeline (real libraries)](#full-pipeline-real-libraries)
- [Running the app](#running-the-app)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Embedders](#embedders)
- [Declaration schema](#declaration-schema)
- [Docker](#docker)
- [Deployment](#deployment)
- [Development](#development)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Supported libraries](#supported-libraries)

---

## Features

- **Dependency-free extraction** — parses `.v` files directly (handles nested
  comments, strings, and statement boundaries). No Rocq/Coq toolchain required.
- **Pluggable embeddings** — `hash` (offline smoke test), `local`
  (sentence-transformers), or `openai`.
- **Vector search** — cosine similarity over Qdrant, with `library` and `kind`
  filters.
- **Rule-based enrichment** — fills missing docstrings and deduplicates
  declarations across libraries.
- **Clean search UI** — debounced search, filters, score bars, and direct
  "View source" links to GitHub.
- **Offline demo corpus** — a curated seed dataset so the app works on a fresh
  clone with zero network access.

---

## Architecture

| Stage | Module | What it does |
|-------|--------|--------------|
| Fetch | `roqet.fetch` | Clone/update known libraries (stdlib, mathcomp, …) |
| Extract | `roqet.extract` | Parse `.v` files into canonical JSONL declarations |
| Enrich | `roqet.enrich` | Generate missing docstrings, dedupe |
| Validate | `roqet.validate` | Inspect/grep a JSONL file from the CLI |
| Embed/Index | `roqet.embedder` | Embed declarations and upsert into Qdrant |
| Serve | `roqet.api` | FastAPI search service (`/search`, `/stats`, …) |
| UI | `app/` + `lib/api.ts` | Next.js front end calling the API |

Shared helpers (canonical schema, GitHub URL building, stable IDs) live in
`roqet.schema`.

For how retrieval actually works — indexing, dense+sparse vectors, ranking, and the
**measured** retrieval quality (including approaches that were tried and rejected) —
see **[SEARCH.md](SEARCH.md)**.

---

## Requirements

- **Python** 3.11+
- **Node.js** 20+ (for the UI)
- **Docker** (optional, for the Compose deployment)

The extractor does **not** require Rocq/Coq to be installed — it is a fast corpus
builder, not a typechecker.

---

## Setup

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate          # or call .venv/bin/python directly
pip install -r requirements.txt    # full deps incl. local/openai embedders
# For a lightweight hash-only install:
#   pip install "fastapi>=0.111" "uvicorn[standard]>=0.29" "qdrant-client>=1.9" "pydantic>=2"

# Frontend
npm install
```

> If you don't activate the venv, prefix Python/uvicorn commands with
> `.venv/bin/` (e.g. `.venv/bin/uvicorn ...`).

---

## Quick start (offline demo)

A small, recognizable demo corpus lives in [`fixtures/seed/`](fixtures/seed/)
with declarations from stdlib, MathComp, UniMath, and HoTT. It needs no network
access and covers every example query in the UI.

**1. Build the index** (extract → enrich → index, ~1 second):

```bash
./scripts/build_index.sh
```

**2. Start the API** (terminal 1):

```bash
ROQET_EMBEDDER=hash .venv/bin/uvicorn roqet.api:app --reload --port 8000
```

**3. Start the UI** (terminal 2):

```bash
npm run dev
```

Open **[http://localhost:3000](http://localhost:3000)** and try a query like
*"commutativity of addition"* or click an example chip.

Quick API-only check (no UI):

```bash
curl "http://localhost:8000/search?q=group+homomorphism+identity&limit=3"
```

> **Note:** the demo uses the `hash` embedder, which is lexical (good enough to
> smoke-test the whole stack). For genuinely semantic results, rebuild with
> `MODEL=local ./scripts/build_index.sh` — see [Embedders](#embedders).

---

## Full pipeline (real libraries)

To index actual libraries instead of the demo corpus:

```bash
# 1. Fetch (shallow clones into ./repos)
python3 -m roqet.fetch --lib stdlib --lib mathcomp

# 2. Extract — point --source at PATH=library_label (repeatable)
python3 -m roqet.extract \
  --source repos/stdlib/theories=stdlib \
  --source repos/mathcomp=mathcomp \
  --out data/declarations.jsonl

# 3. Enrich + dedupe
python3 -m roqet.enrich \
  --input data/declarations.jsonl \
  --out data/declarations.enriched.jsonl \
  --dedupe

# 4. Inspect quality (optional)
python3 -m roqet.validate --file data/declarations.enriched.jsonl
python3 -m roqet.validate --file data/declarations.enriched.jsonl --search commut --kind Lemma

# 5. Index
python3 -m roqet.embedder \
  --input data/declarations.enriched.jsonl \
  --model local \
  --reset
```

You can also point `--source` at any local `.v` tree:

```bash
python3 -m roqet.extract --source ~/code/UniMath/UniMath=unimath --out data/declarations.jsonl
```

Or drive the whole chain through the build script with overrides:

```bash
SOURCES="--source repos/stdlib/theories=stdlib" MODEL=local ./scripts/build_index.sh
```

---

## Running the app

Use the helper script or run the commands directly.

```bash
./deploy.sh api      # FastAPI on :8000 (uses ROQET_EMBEDDER, default hash)
./deploy.sh ui       # Next.js dev server on :3000
./deploy.sh docker   # Build + run everything via Docker Compose
```

> `deploy.sh api` calls bare `uvicorn`, so activate the venv first
> (`source .venv/bin/activate`) or run `.venv/bin/uvicorn roqet.api:app --port 8000`.

The API embedder **must match** the embedder used at index time (same model →
same vector dimensions). If you indexed with `--model local`, serve with
`ROQET_EMBEDDER=local`.

---

## API reference

Base URL defaults to `http://localhost:8000`.

### `GET /health`
Liveness probe.
```json
{ "status": "ok", "collection": "roqet_declarations" }
```

### `GET /search`
Semantic search.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | — (required) | Natural-language query |
| `limit` | int | 10 | Results to return (1–50) |
| `lib` | string | — | Filter by library; comma-separated for multiple |
| `kind` | string | — | Filter by kind (e.g. `Lemma,Theorem`) |

```bash
curl "http://localhost:8000/search?q=list+append+associativity&lib=stdlib&kind=Lemma&limit=5"
```
Response:
```json
{
  "query": "list append associativity",
  "results": [
    {
      "name": "app_assoc", "kind": "Lemma",
      "type_signature": "...", "docstring": "...",
      "module_path": "theories.Lists.List", "library": "stdlib",
      "file_path": "theories/Lists/List.v", "line_number": 3,
      "github_url": "https://github.com/...#L3", "score": 0.74
    }
  ],
  "total": 1, "elapsed_ms": 2.6
}
```

### `GET /libs`
Per-library counts.
```json
{ "libraries": { "stdlib": 15, "mathcomp": 10 } }
```

### `GET /stats`
Index summary.
```json
{ "total_points": 33, "libraries": { "...": 0 }, "kinds": { "Lemma": 26 } }
```

---

## MCP server

Roqet ships an [MCP](https://modelcontextprotocol.io) server so LLM agents (Claude
Desktop, Claude Code, …) can search the libraries by *meaning* as a tool — the
semantic layer the Rocq MCP ecosystem otherwise lacks. It complements proof-loop
servers like [rocq-mcp](https://github.com/LLM4Rocq) (which wrap `coqc`'s exact
keyword `Search`).

It's a **thin client** over the HTTP API above — point it at any running Roqet API
with `ROQET_API_URL`. Use the hosted backend (no setup), or your own local one.

```bash
# Install the package (this is what provides the `roqet-mcp` command):
pip install -e ".[mcp]"

# Point at the hosted backend (recommended — nothing else to run):
ROQET_API_URL=https://roqet-production-b979.up.railway.app roqet-mcp     # stdio transport

# ...or at a backend you're running locally:
ROQET_API_URL=http://localhost:8000 roqet-mcp
```

> `pip install -r requirements-mcp.txt` installs only the dependencies (`mcp`,
> `httpx`); it does **not** create the `roqet-mcp` command. Use `pip install -e ".[mcp]"`,
> or run the module directly with `python -m roqet.mcp_server`.

Tools exposed:
- **`roqet_search(query, lib?, kind?, limit?)`** — semantic search; returns matching
  declarations with type signatures, statements, and source links.
- **`roqet_stats()`** — what the index currently contains.

### Register with a client

Claude Code (point `ROQET_API_URL` at the hosted backend, or your local one):
```bash
claude mcp add roqet --env ROQET_API_URL=https://roqet-production-b979.up.railway.app -- roqet-mcp
```

Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "roqet": {
      "command": "roqet-mcp",
      "env": { "ROQET_API_URL": "https://roqet-production-b979.up.railway.app" }
    }
  }
}
```
(If `roqet-mcp` isn't on PATH, use the absolute path to it, or
`"command": "python", "args": ["-m", "roqet.mcp_server"]`.)

---

## Configuration

All configuration is via environment variables.

### Backend (indexing + API)

| Variable | Default | Used by | Description |
|----------|---------|---------|-------------|
| `ROQET_EMBEDDER` | `hash` | API | Query embedder: `hash`, `local` (torch), `fastembed` (ONNX, low-RAM, used in hosting), or `openai` |
| `ROQET_SEARCH` | `dense` | API | Retrieval: `dense` (semantic, default) or `fusion` (dense+BM25 sparse RRF) |
| `ROQET_RERANK` | `auto` | API | Reorder of retrieved candidates: `auto`/`lexical` = dense+lexical RRF (default); `cross` = cross-encoder; `off` = none |
| `ROQET_RERANK_CANDIDATES` | `40` | API | Candidates fetched before reranking |
| `QDRANT_URL` | _(unset)_ | both | Remote Qdrant URL; if unset, uses on-disk store |
| `QDRANT_PATH` | `data/qdrant_storage` | both | Local on-disk Qdrant path |
| `QDRANT_API_KEY` | _(unset)_ | both | API key for a managed Qdrant |
| `ROQET_COLLECTION` | `roqet_declarations` | both | Qdrant collection name |
| `ROQET_BATCH_SIZE` | `64` | indexer | Embedding batch size |
| `EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | local embedder | sentence-transformers model |
| `EMBED_MAX_SEQ_LENGTH` | `512` | local embedder | Token cap per declaration (guards against huge inputs) |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | openai embedder | OpenAI model |
| `OPENAI_API_KEY` | _(unset)_ | openai embedder | Required for `--model openai` |
| `CORS_ORIGINS` | `*` | API | Comma-separated allowed origins |
| `ROQET_RATE_LIMIT` | `60` | API | Max `/search` requests per minute per IP (0 disables) |

### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API base URL the UI calls |

---

## Embedders

Choose with `--model` at index time (and the matching `ROQET_EMBEDDER` at serve
time).

| Model | Deps | Dim | Use case |
|-------|------|-----|----------|
| `hash` | none | 384 | Offline smoke tests / demo. Lexical, deterministic. |
| `local` | `sentence-transformers` (torch) | model-dependent | Real semantic quality; heavier RAM/image. |
| `fastembed` | `fastembed` (ONNX) | 384 | Same MiniLM via ONNX — low RAM, used for hosting. |
| `openai` | `openai` + `OPENAI_API_KEY` | 1536/3072 | Highest quality, hosted, paid. |

```bash
# Local model
python3 -m roqet.embedder --input data/declarations.enriched.jsonl --model local --reset

# OpenAI
OPENAI_API_KEY=sk-... python3 -m roqet.embedder \
  --input data/declarations.enriched.jsonl --model openai --reset
```

Indexer flags: `--reset` (recreate the collection), `--no-resume` (re-index
everything instead of skipping already-indexed declarations), `--qdrant-url`.

---

## Declaration schema

Each JSONL record (and search result) uses this canonical shape:

```json
{
  "name": "addnC",
  "kind": "Lemma",
  "type_signature": "commutative addn",
  "statement": "Lemma addnC : commutative addn.",
  "docstring": "Addition is commutative.",
  "module_path": "ssreflect.ssrnat",
  "library": "mathcomp",
  "file_path": "ssreflect/ssrnat.v",
  "source_path": "/absolute/path/to/ssrnat.v",
  "line_number": 123,
  "github_url": "https://github.com/math-comp/math-comp/blob/master/ssreflect/ssrnat.v#L123"
}
```

`roqet.schema.normalize_declaration` also accepts an older prototype shape
(`type`/`doc`/`module`/`file`/`line`) and normalizes it.

---

## Docker

```bash
docker compose up --build
```

This starts three services:

| Service | Port | Description |
|---------|------|-------------|
| `qdrant` | 6333 | Vector database |
| `api` | 8000 | FastAPI search service (`ROQET_EMBEDDER=hash`) |
| `ui` | 3000 | Next.js UI |

The containers start empty — index into the running Qdrant from the host:

```bash
QDRANT_URL=http://localhost:6333 python3 -m roqet.embedder \
  --input data/declarations.enriched.jsonl --model hash --reset
```

---

## Deployment

`railway.toml` is a starting point for [Railway](https://railway.app): it builds
the API from `Dockerfile.api`, serves with `uvicorn api:app`, and health-checks
`/health`. Set `QDRANT_URL`, `QDRANT_API_KEY`, `ROQET_EMBEDDER`, and any model
keys in the Railway dashboard. Use a managed Qdrant (e.g. Qdrant Cloud) rather
than the on-disk store for hosted deployments.

---

## Development

```bash
# Run the test suite
python3 -m unittest discover -s tests
# or, with pytest installed:
pip install -r requirements-dev.txt && pytest -q

# Lint
ruff check .
```

Console scripts (after `pip install -e .`):
`roqet-fetch`, `roqet-extract`, `roqet-enrich`, `roqet-index`, `roqet-validate`.

---

## Project layout

```
roqet/                 Python package
  schema.py            Canonical schema, GitHub URLs, stable IDs
  fetch.py             Clone/update libraries
  extract.py           .v parser → JSONL
  enrich.py            Docstring generation + dedupe
  validate.py          CLI inspector
  embedder.py          Embedders + Qdrant indexing
  api.py               FastAPI service
app/                   Next.js app (layout, page, styles)
lib/api.ts             Front-end API client + constants
fixtures/seed/         Offline demo corpus (committed)
scripts/build_index.sh One-command pipeline
tests/                 unittest suite
data/                  Generated JSONL + Qdrant store (gitignored)
api.py, embedder.py …  Thin root wrappers for the roqet.* modules
Dockerfile*, docker-compose.yml, railway.toml, deploy.sh
```

---

## Troubleshooting

**`Storage folder data/qdrant_storage is already accessed by another instance`**
The on-disk Qdrant allows one process at a time. Stop the API before
(re)building the index:
```bash
pkill -f "uvicorn roqet"
rm -f data/qdrant_storage/.lock   # only if a stale lock remains
```
For concurrent access, run a Qdrant server and set `QDRANT_URL`.

**`command not found: uvicorn` / `No module named fastapi`**
The deps live in the venv. Activate it (`source .venv/bin/activate`) or call
`.venv/bin/uvicorn` / `.venv/bin/python`.

**Search returns empty / irrelevant results**
Confirm the index has points (`curl localhost:8000/stats`) and that
`ROQET_EMBEDDER` matches the model used to build the index. The `hash` embedder
is lexical — switch to `local`/`openai` for semantic quality.

**UI can't reach the API**
Check the API is on `:8000` and `NEXT_PUBLIC_API_URL` points at it. CORS is open
(`*`) by default.

---

## Supported libraries

The fetch helper knows about:

| Key | Library | Source |
|-----|---------|--------|
| `stdlib` | Rocq standard library | rocq-prover/stdlib |
| `mathcomp` | Mathematical Components | math-comp/math-comp |
| `unimath` | UniMath | UniMath/UniMath |
| `hott` | HoTT | HoTT/Coq-HoTT |
| `iris` | Iris | gitlab.mpi-sws.org/iris/iris |

A later quality pass can swap the regex extractor for `coq-lsp` or SerAPI to get
fully elaborated declarations.
