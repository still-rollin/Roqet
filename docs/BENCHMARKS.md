# Benchmarks

Retrieval-quality experiments on Rocqet. Each entry states the question, the
exact (leakage-controlled) methodology, the numbers, and how to reproduce them.

---

## 1. Do natural-language descriptions fix MathComp search? (2026-06)

**Context.** MathComp is the hardest library for semantic search: identifiers are
terse (`rVpoly`, `addrA`), statements are notation-heavy (`\poly_(k < d) ...`), and
there is essentially no prose. A generic sentence-embedding model has almost no
natural-language surface to match a user's query against. We obtained a
description corpus covering **22,803 MathComp declarations** (one informal English
sentence each) and attached it to **96%** of the 19,448 indexed MathComp decls.

**Question.** If we embed those descriptions into each declaration's document
text, how much does natural-language → lemma retrieval improve?

### Methodology (leakage-controlled)

- **Eval set:** 292 MathComp declarations with unambiguous names. Gold = the
  declaration; query = a natural-language phrasing of it.
- **The leakage trap & fix.** Using a declaration's own description *verbatim* as
  its query is leaky — that exact text is embedded into the doc, so retrieval is
  trivial. We therefore report two query forms:
  - *verbatim* — the description as-is (a **leaky upper bound**, not the result);
  - *paraphrase* — each description rewritten by an LLM into a short, search-box
    style query, **with no Coq identifier names** and different wording (the
    honest number; this mirrors the LeanSearch / Lean Finder eval style).
- **Two indexes, identical except for descriptions:** `base` (name + type +
  statement, no descriptions) vs `ship` (descriptions embedded). Same 19,448
  decls, same model (`fastembed`, MiniLM-L6 384-d), same rerank. So any delta is
  the descriptions alone.
- **No production contamination:** the A/B ran in dedicated Qdrant collections
  (`rocqet_mc_base`, `rocqet_mc_ship`), never the live collection.

### Results (292 queries, hit@k = gold in top-k)

| query form | index | hit@1 | hit@5 | hit@10 | MRR@10 |
|---|---|---|---|---|---|
| paraphrase (**honest**) | base (no desc) | 0.065 | 0.164 | 0.205 | 0.116 |
| paraphrase (**honest**) | **ship (desc)** | **0.353** | **0.709** | **0.853** | **0.512** |
| verbatim (leaky ceiling) | base (no desc) | 0.003 | 0.021 | 0.048 | 0.015 |
| verbatim (leaky ceiling) | ship (desc) | 0.644 | 0.908 | 0.986 | 0.760 |

**Headline (honest, same paraphrase queries on both indexes):** embedding the
descriptions lifts every metric **~4–5×** — hit@10 **0.205 → 0.853**, hit@1
**0.065 → 0.353**, MRR **0.116 → 0.512**.

### Per-topic (honest paraphrase, ship index), hit@10

| module | hit@10 |
|---|---|
| algebra | 95/113 |
| boot | 59/71 |
| field | 6/10 |
| finite_group | 27/30 |
| group_representation | 28/29 |
| order | 11/14 |
| solvable | 23/25 |

### Takeaways

- The MathComp weakness was a **missing natural-language surface**, not an
  extraction or ranking bug. Descriptions supply exactly that surface.
- The gain holds under a genuinely held-out, identifier-free, reworded query set,
  so it reflects real user phrasings — not memorized text.
- Same recipe should transfer to the other libraries once they have comparable
  descriptions.

### Reproduce

```bash
# 1. Build the corpora (base / enriched / ship) + the 292-query eval set
python scripts/attach_mathcomp_nl.py

# 2. A/B the two indexes in throwaway collections (needs QDRANT_URL / QDRANT_API_KEY)
./scripts/eval_mathcomp_ab.sh                # -> base vs enriched on verbatim queries

# 3. Honest number: rewrite descriptions into short search queries, then eval
GEMINI_API_KEYS=key1,key2 python scripts/make_query_eval.py
ROCQET_COLLECTION=rocqet_mc_base ROCQET_EMBEDDER=fastembed \
  python -m rocqet.eval --eval-type nl --eval data/eval/nl_queries_mathcomp_q.jsonl
ROCQET_COLLECTION=rocqet_mc_ship ROCQET_EMBEDDER=fastembed \
  python -m rocqet.eval --eval-type nl --eval data/eval/nl_queries_mathcomp_q.jsonl
```

The description corpus (`data/mathcomp-natural-lang.json`) and generated datasets
are distributed as release assets, not committed (see [DATA.md](DATA.md)).

---

## 2. Does a domain fine-tune add to the descriptions? (2026-07)

**Context.** Descriptions fixed the *missing-surface* problem (§1): the right
neighborhood now lands in the top-10 (hit@10 0.85). What they don't fully fix is
*discrimination* — for a short query the exact lemma isn't always #1 (hit@1 ≈ 0.35),
because a generic model still weights the concept noun over the relation
(`same_env` vs `same_env_sym`, `eval` vs `eval_tsubst`).

**Question.** Does a small contrastive fine-tune with hard negatives — on top of the
descriptions — push the exact lemma up (hit@1 / MRR), without a bigger/heavier model?

### Methodology

- **Model.** Fine-tune `all-MiniLM-L6-v2` (384-d, the served model) with
  `MultipleNegativesRankingLoss`; base unchanged so serving is unchanged.
- **Data.** `rocqet.finetune` pairs: anchor = NL description, positive = the
  declaration, **hard negatives = same concept-stem / different relation** (the
  model's actual confusions). ~16k train rows, 65% with hard negatives.
- **Leakage control.** `--holdout-eval` forces every eval gold's *cluster* out of
  training (verified **0 of 292** eval golds leak into train).
- **Fair A/B.** Both indexes = the same enriched (ship) corpus, both via the `local`
  embedder, same 292 held-out paraphrase queries. Only the weights differ.

### Results (292 queries)

| index (same enriched corpus) | hit@1 | hit@5 | hit@10 | MRR@10 |
|---|---|---|---|---|
| base all-MiniLM (descriptions only) | 0.377 | 0.723 | 0.839 | 0.523 |
| **+ contrastive fine-tune** | **0.452** | **0.767** | **0.873** | **0.592** |

**Fine-tune lift on top of descriptions:** hit@1 **+20%** (0.377 → 0.452), MRR
**+13%** (0.523 → 0.592), hit@10 +4% (already near-saturated by descriptions). The
gain concentrates exactly where predicted — **reordering within the right
neighborhood to pin the exact lemma at #1** — which is what hit@1 / MRR measure.

### Full progression (honest paraphrase queries, hit@10 / hit@1 / MRR)

| stage | hit@1 | hit@10 | MRR@10 |
|---|---|---|---|
| baseline (no descriptions) | 0.065 | 0.205 | 0.116 |
| + NL descriptions (shipped) | 0.377 | 0.839 | 0.523 |
| + domain fine-tune | **0.452** | **0.873** | **0.592** |

Two independent, measured wins: descriptions (~4× recall) and a lightweight
domain fine-tune (+20% exact-match), both leakage-controlled on held-out queries.

### Reproduce

```bash
python -m rocqet.finetune --input data/declarations.mathcomp.ship.jsonl \
  --holdout-eval data/eval/nl_queries_mathcomp_q.jsonl        # build train/test
python scripts/train_embed.py --train data/finetune/train.jsonl --out models/rocqet-embed
./scripts/eval_finetune.sh                                     # base vs tuned A/B
```

See [FINETUNE.md](FINETUNE.md) for the full pipeline. Production still serves the
description-only index; shipping the fine-tuned weights (ONNX → fastembed) is the
next step, gated on this win.
