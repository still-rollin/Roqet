#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Roqet deployment helper

Commands:
  ./deploy.sh docker     Build and run Qdrant, API, and UI with Docker Compose
  ./deploy.sh api        Run the FastAPI server locally
  ./deploy.sh ui         Run the Next.js UI locally

Before deploying, generate and index data:
  python3 -m roqet.fetch --lib stdlib --lib mathcomp
  python3 -m roqet.extract --source repos/stdlib/theories=stdlib --source repos/mathcomp=mathcomp --out data/declarations.jsonl
  python3 -m roqet.enrich --input data/declarations.jsonl --out data/declarations.enriched.jsonl --dedupe
  python3 -m roqet.embedder --input data/declarations.enriched.jsonl --model hash --reset
EOF
}

case "${1:-}" in
  docker)
    docker compose up --build
    ;;
  api)
    ROQET_EMBEDDER="${ROQET_EMBEDDER:-hash}" uvicorn roqet.api:app --reload --port "${PORT:-8000}"
    ;;
  ui)
    npm run dev
    ;;
  *)
    usage
    ;;
esac
