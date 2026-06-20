#!/usr/bin/env bash
#
# Reproducibly build the Rocqet deploy dataset: deploy/declarations.enriched.jsonl
#
# This is the prebuilt artifact attached to GitHub Releases. It is a *build
# output* and is intentionally NOT committed to git (see .gitignore). Either
# download it from the latest Release, or regenerate it here:
#
#   ./scripts/build_dataset.sh
#
# Pipeline: fetch library checkouts -> extract declarations (GeoCoq curated)
# -> enrich + dedupe -> deploy/declarations.enriched.jsonl. No Rocq toolchain
# needed; extraction is pure parsing. Re-run to refresh after upstream changes.
#
# Env:
#   PYTHON   interpreter (default: .venv/bin/python if present, else python3)
#   LIBS     space-separated libraries to include
#            (default: stdlib mathcomp mathcomp-analysis geocoq)

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  if [[ -x .venv/bin/python ]]; then PYTHON=".venv/bin/python"; else PYTHON="python3"; fi
fi

LIBS="${LIBS:-stdlib mathcomp mathcomp-analysis geocoq}"
OUT="deploy/declarations.enriched.jsonl"
mkdir -p deploy data

echo "==> Fetching libraries: ${LIBS}"
FETCH_ARGS=()
for lib in ${LIBS}; do FETCH_ARGS+=(--lib "${lib}"); done
"${PYTHON}" -m rocqet.fetch "${FETCH_ARGS[@]}"

echo "==> Extracting declarations"
: > data/declarations.jsonl
for lib in ${LIBS}; do
  case "${lib}" in
    stdlib)            SRC="repos/stdlib/theories=stdlib" ;;
    mathcomp)          SRC="repos/mathcomp=mathcomp" ;;
    mathcomp-analysis) SRC="repos/mathcomp-analysis=mathcomp-analysis" ;;
    unimath)           SRC="repos/unimath/UniMath=unimath" ;;
    hott)              SRC="repos/hott/theories=hott" ;;
    geocoq)
      # GeoCoq: curated subdirs + only Lemma/Theorem/Definition/Corollary
      # (the repo is full of Ltac/tactic noise). Chapter is derived from filenames.
      "${PYTHON}" -m rocqet.extract \
        --source repos/geocoq/theories=geocoq \
        --include Main/Tarski_dev --include Main/Highschool --include Main/Utils \
        --include Axioms --include Elements \
        --kinds Lemma,Theorem,Definition,Corollary \
        --append --out data/declarations.jsonl
      continue ;;
    *) echo "!! unknown library '${lib}', skipping"; continue ;;
  esac
  "${PYTHON}" -m rocqet.extract --source "${SRC}" --append --out data/declarations.jsonl
done

echo "==> Enriching + deduplicating -> ${OUT}"
"${PYTHON}" -m rocqet.enrich --input data/declarations.jsonl --out "${OUT}" --dedupe

COUNT=$(wc -l < "${OUT}" | tr -d ' ')
echo "==> Done. ${OUT} (${COUNT} declarations)."
echo "    Index it into managed Qdrant with ./scripts/index_cloud.sh"
