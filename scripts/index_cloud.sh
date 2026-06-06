#!/usr/bin/env bash
#
# One-time: build the Roqet index into a managed (remote) Qdrant cluster, e.g.
# Qdrant Cloud's free tier. The hosted API then connects to that cluster instead
# of holding the vector DB in-process, keeping its memory small.
#
# Usage:
#   export QDRANT_URL="https://xxxx.cloud.qdrant.io:6333"
#   export QDRANT_API_KEY="..."
#   ./scripts/index_cloud.sh
#
# Re-run after refreshing deploy/declarations.enriched.jsonl. Uses fastembed so
# the vectors match what the hosted API produces at query time.

set -euo pipefail
cd "$(dirname "$0")/.."

: "${QDRANT_URL:?set QDRANT_URL to your managed Qdrant endpoint}"
: "${QDRANT_API_KEY:?set QDRANT_API_KEY for your managed Qdrant}"

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  if [[ -x .venv/bin/python ]]; then PYTHON=".venv/bin/python"; else PYTHON="python3"; fi
fi

echo "==> Indexing deploy snapshot into ${QDRANT_URL} (fastembed)"
"${PYTHON}" -m roqet.embedder \
  --input deploy/declarations.enriched.jsonl \
  --model fastembed \
  --qdrant-url "${QDRANT_URL}" \
  --reset

echo "==> Done. Set QDRANT_URL and QDRANT_API_KEY in the Railway service, then redeploy."
