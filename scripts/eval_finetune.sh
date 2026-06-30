#!/usr/bin/env bash
#
# Measure the fine-tuned rocqet-embed model against the description-only baseline,
# both on the SAME enriched (ship) corpus and the SAME held-out paraphrase queries —
# so the only variable is the model weights. Answers: does contrastive fine-tuning
# add anything on top of the descriptions (which already gave hit@10 0.853)?
#
# Uses the `local` (sentence-transformers) embedder so no ONNX export is needed yet;
# ONNX/fastembed is only for the production ship, and only if this wins.
#
# Prereqs:
#   - models/rocqet-embed/   (download the Colab-trained model here)
#   - QDRANT_URL / QDRANT_API_KEY exported
#   - data/declarations.mathcomp.ship.jsonl + data/eval/nl_queries_mathcomp_q.jsonl
#
#   ./scripts/eval_finetune.sh
#   STEP=eval ./scripts/eval_finetune.sh        # skip re-indexing

set -euo pipefail
cd "$(dirname "$0")/.."
: "${QDRANT_URL:?set QDRANT_URL}"; : "${QDRANT_API_KEY:?set QDRANT_API_KEY}"
PY="${PYTHON:-.venv/bin/python}"; [[ -x "$PY" ]] || PY="python3"
SHIP="data/declarations.mathcomp.ship.jsonl"
EVAL="data/eval/nl_queries_mathcomp_q.jsonl"
BASE="sentence-transformers/all-MiniLM-L6-v2"
TUNED="models/rocqet-embed"
STEP="${STEP:-all}"

index() {  # $1 collection  $2 EMBED_MODEL
  echo "==> indexing $SHIP with model=$2 -> $1"
  ROCQET_COLLECTION="$1" EMBED_MODEL="$2" "$PY" -m rocqet.embedder \
    --input "$SHIP" --model local --qdrant-url "$QDRANT_URL" --no-resume --reset
}
evaluate() {  # $1 collection  $2 EMBED_MODEL  $3 label
  echo; echo "########  $3  ########"
  ROCQET_COLLECTION="$1" EMBED_MODEL="$2" ROCQET_EMBEDDER=local "$PY" -m rocqet.eval \
    --eval-type nl --eval "$EVAL"
}

[[ -d "$TUNED" ]] || { echo "!! $TUNED not found — train on Colab (scripts/train_embed.py) and download it here"; exit 1; }

if [[ "$STEP" != "eval" ]]; then
  index rocqet_mc_base_local "$BASE"
  index rocqet_mc_tuned      "$TUNED"
fi
evaluate rocqet_mc_base_local "$BASE"  "A) BASE all-MiniLM (descriptions only)"
evaluate rocqet_mc_tuned      "$TUNED" "B) FINE-TUNED rocqet-embed (descriptions + contrastive)"
echo; echo "B - A on hit@1 / MRR = the fine-tune lift on top of descriptions."
