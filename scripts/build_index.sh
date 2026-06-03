#!/usr/bin/env bash
#
# Build a searchable Roqet index.
#
# By default this indexes the small, offline demo corpus in fixtures/seed,
# which contains recognizable declarations from each supported library and
# requires no network access. This is enough to run the UI and exercise every
# example query out of the box.
#
# To index real libraries instead, fetch them first and point this at the
# checkouts, e.g.:
#
#   python3 -m roqet.fetch --lib stdlib --lib mathcomp
#   SOURCES="--source repos/stdlib/theories=stdlib --source repos/mathcomp=mathcomp" \
#     ./scripts/build_index.sh
#
# Environment variables:
#   PYTHON     Python interpreter to use (default: python3, or .venv/bin/python if present)
#   MODEL      Embedder: hash | local | openai (default: hash)
#   SOURCES    Override the --source arguments passed to the extractor
#   QDRANT_URL Index into a remote Qdrant instead of the local on-disk store

set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  if [[ -x .venv/bin/python ]]; then PYTHON=".venv/bin/python"; else PYTHON="python3"; fi
fi

MODEL="${MODEL:-hash}"

DEFAULT_SOURCES="--source fixtures/seed/stdlib=stdlib \
--source fixtures/seed/mathcomp=mathcomp \
--source fixtures/seed/unimath=unimath \
--source fixtures/seed/hott=hott"
SOURCES="${SOURCES:-$DEFAULT_SOURCES}"

RESET_FLAG="--reset"
QDRANT_FLAG=""
if [[ -n "${QDRANT_URL:-}" ]]; then
  QDRANT_FLAG="--qdrant-url ${QDRANT_URL}"
fi

echo "==> Extracting declarations"
# shellcheck disable=SC2086
"${PYTHON}" -m roqet.extract ${SOURCES} --out data/declarations.jsonl

echo "==> Enriching and deduplicating"
"${PYTHON}" -m roqet.enrich \
  --input data/declarations.jsonl \
  --out data/declarations.enriched.jsonl \
  --dedupe

echo "==> Indexing into Qdrant (model: ${MODEL})"
# shellcheck disable=SC2086
"${PYTHON}" -m roqet.embedder \
  --input data/declarations.enriched.jsonl \
  --model "${MODEL}" \
  ${QDRANT_FLAG} \
  ${RESET_FLAG}

echo "==> Done. Start the API with:  ./deploy.sh api"
