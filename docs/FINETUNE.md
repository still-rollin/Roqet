# Fine-tuning rocqet-embed

Descriptions took MathComp NL search from hit@10 0.205 → **0.853** (see
[BENCHMARKS.md](BENCHMARKS.md)). What's left is the **discrimination** gap: for a
short query the *right neighborhood* comes back, but the exact lemma isn't always
#1 (hit@1 ≈ 0.35) — the model still weights the concept noun over the relation
(`group homomorphism` matched, `maps identity to identity` not pinned to `morph1`).

Fine-tuning fixes exactly that: a contrastive objective that pulls the query toward
its lemma and pushes it away from same-concept / different-relation siblings, so the
model is forced to encode the relation. Base model: **all-MiniLM-L6-v2 (384-d)** —
the one we already serve, so serving is unchanged (only the weights move).

## Pipeline

```
rocqet.finetune  ──>  train.jsonl / test.jsonl      (pairs + hard negatives, cluster-safe)
scripts/train_embed.py  ──>  models/rocqet-embed     (Colab free GPU, ~10-30 min)
scripts/eval_finetune.sh  ──>  base vs tuned numbers (local embedder, no ONNX yet)
[only if it wins]  scripts/export_onnx.py  ──>  fastembed serving on Railway
```

### 1. Build training data (local)

```bash
python -m rocqet.finetune \
  --input data/declarations.mathcomp.ship.jsonl \
  --holdout-eval data/eval/nl_queries_mathcomp_q.jsonl
```

- **Anchors** = the real NL descriptions (96% coverage); positives = the declaration
  doc text; **hard negatives** = same concept-stem, different relation
  (`same_env` vs `same_env_sym`, `eval` vs `eval_tsubst`) — the model's actual
  confusions, mined by `rocqet.finetune`.
- `--holdout-eval` forces every eval gold's *cluster* out of training, so the
  post-tune NL eval is leakage-free (verified: 0 of 292 golds leak into train).
- Output: `data/finetune/{train,test}.jsonl` (~16k train rows, 65% with hard negs).

### 2. Train on Colab (free T4)

Upload `data/finetune/train.jsonl` and `scripts/train_embed.py`, then:

```python
!pip install -U sentence-transformers datasets
!python train_embed.py --train train.jsonl --out rocqet-embed --epochs 1 --batch-size 64
```

Zip and download `rocqet-embed/` into `models/rocqet-embed/` locally. (1 epoch is a
sensible first run; bump `--epochs 2-3` if the eval improves and isn't overfitting.)

### 3. Evaluate (local, no ONNX needed)

`EMBED_MODEL` makes the `local` embedder load any path, so we can index + eval the
tuned model directly:

```bash
export QDRANT_URL=... QDRANT_API_KEY=...
./scripts/eval_finetune.sh
```

This indexes the **same enriched corpus** twice — base all-MiniLM vs tuned — into
throwaway collections and evals both on the 292 held-out paraphrase queries. The
delta is the fine-tune lift **on top of** descriptions. Target: hit@1 0.35 → 0.5+,
hit@10 0.85 → 0.9+.

### 4. Ship (only if it wins)

Production serves `fastembed` (ONNX, low RAM) to fit Railway. Export the tuned model
to ONNX and register it with fastembed, then re-index `rocqet_declarations`. This is
deferred until step 3 shows a real gain — don't productionize a model that didn't win.

## Notes

- **Why MiniLM, not bge-base?** Drop-in serving (same 384-d, same fastembed path),
  zero infra change. A stronger base (bge) or a distilled 7B teacher are later levers.
- **v2 ideas if hit@1 plateaus:** add short synthesized query anchors (not just full
  descriptions) so training matches real short queries; add embedding-based hard
  negatives (base-model nearest neighbors minus gold); wire in the 4,500 premise pairs.
- Training artifacts under `data/finetune/` and `models/` are gitignored.
