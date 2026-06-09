# Search engineering

How Roqet actually finds declarations: what gets indexed, how a query is served,
the ranking choices, and the **measured** retrieval quality — including the
approaches that were tried and rejected.

> TL;DR — Roqet retrieves with a dense semantic vector (MiniLM, 384-d, cosine over
> Qdrant), then reorders the top candidates with a dependency-free lexical
> Reciprocal-Rank-Fusion pass. A BM25 sparse vector is also indexed and a full
> dense+sparse fusion mode exists, but **equal-weight fusion measured worse** on
> natural-language queries, so dense+lexical is the shipped default.

---

## 1. The pipeline at a glance

```
INDEX TIME                                   QUERY TIME
.v files                                     "addition is commutative"
   │ extract  (regex parser)                    │ embed query (same model)
   ▼                                            ▼
declaration record ──┐                       dense vector ──┐
   │ enrich/dedupe    │ declaration_text()       sparse vec ─┤ (lexical / fusion)
   ▼                  ▼                                       ▼
   ├─ dense vector  (MiniLM/ONNX, 384-d) ──▶ Qdrant ◀── retrieve top-N candidates
   └─ sparse vector (BM25 tokens, IDF)   ──▶  (named         │
                                              dense+sparse)   ▼ rerank (RRF) → top-K
```

Two representations are stored per declaration; retrieval picks the dense one by
default and lets a lexical pass break ties.

---

## 2. What gets embedded

A declaration is flattened to a single string by
[`declaration_text`](roqet/schema.py) — this is the text the **dense** model sees:

```
{kind} {name} | {type_signature} | {docstring} | {statement} | module {module_path} | library {library}
```

e.g. `Lemma addnC | commutative addn | Addition is commutative. | Lemma addnC : commutative addn. | module ssreflect.ssrnat | library mathcomp`

The **sparse** (keyword) side uses a tighter field set —
[`sparse_text`](roqet/schema.py) = `name + type_signature + statement + docstring`
(no module/library noise).

> **Known weakness:** many records have an *auto-generated* docstring that just
> restates the signature (`"Lemma X: <sig>"`). It's redundant rather than
> informative — terse, symbolic declarations give the embedder thin signal. This
> is the single biggest lever for future quality (see §7).

---

## 3. Indexing

[`roqet.embedder`](roqet/embedder.py) writes each declaration into Qdrant as one
point with **named vectors**:

| Vector | Name | How it's built | Distance |
|--------|------|----------------|----------|
| Dense | `dense` | embedder model over `declaration_text` | Cosine |
| Sparse | `text` | BM25-style term frequencies over `sparse_text` | Dot, **IDF-weighted** |

**Sparse construction** ([`sparse_vector`](roqet/schema.py)):
1. Tokenize: alphanumeric tokens, plus snake_case/CamelCase splits of identifiers
   (`addnC → addn, c`), lowercased, length ≥ 2.
2. Hash each token → a stable 32-bit index (`sha256(token)[:4] % 2³¹`). No
   vocabulary to persist; index and query use the same hash.
3. Value = term frequency. The collection is created with `Modifier.IDF`, so
   **Qdrant applies inverse-document-frequency weighting at query time** — i.e.
   real BM25-like scoring with zero external state.

Point `id` is a deterministic hash of `library:file:line:name`
([`stable_id`](roqet/schema.py)), so re-indexing updates in place instead of
duplicating.

### Embedders (dense)

Chosen with `--model` at index time; the API must serve with the **same** model
(vectors are otherwise incomparable).

| Model | Backend | Dim | Notes |
|-------|---------|-----|-------|
| `hash` | none | 384 | Lexical bag-of-words hash. Smoke tests only. |
| `local` | sentence-transformers (torch) | 384 | MiniLM. Best quality of the MiniLM options; heavy RAM. |
| `fastembed` | fastembed (ONNX) | 384 | Same MiniLM weights via ONNX. **Used in production** (low RAM). |
| `openai` | OpenAI API | 1536/3072 | Highest quality; paid, network. |

Production runs `fastembed` for memory reasons (see [DEPLOY.md](DEPLOY.md)).

---

## 4. Query-time retrieval

[`/search`](roqet/api.py) → `query_points()`:

1. Embed the query string with the active embedder.
2. **Retrieve candidates** (`ROQET_SEARCH`, default `dense`):
   - **`dense`** — cosine k-NN over the `dense` vector, fetching a pool of
     `max(limit, 40)` candidates.
   - **`fusion`** — Qdrant Query API with two prefetches (dense + sparse) fused
     by **Reciprocal Rank Fusion** server-side. *(Off by default — see §6.)*
3. **Rerank** the pool ([`roqet.rerank`](roqet/rerank.py)) down to `limit`.
4. Apply `lib` / `kind` filters as Qdrant payload conditions on the prefetch.

### Reranking (`ROQET_RERANK`, default `auto` = lexical)

The default reorders the dense candidate pool by fusing two rankings with RRF
(`score = 1/(k+rank_dense) + 1/(k+rank_lexical)`, `k=60`):

- **Dense rank** — the order Qdrant returned.
- **Lexical rank** — overlap between query terms and the declaration's tokens:
  full-token match = 1.0; a *targeted* prefix match (≥5 chars, e.g.
  `commut`↔`commutative`, `inject`↔`injective`) = 0.5.

Because lexical only **reorders dense's already-semantically-relevant pool**, it
sharpens keyword/identifier matches without dragging in off-topic results. Modes:
`auto`/`lexical` (default), `cross` (cross-encoder), `off` (trust dense order).

Display scores are the fused score normalized so the top hit = 1.0 — a *relative*
gradient within a result list, **not** an absolute confidence.

---

## 5. Measured quality

Method: 15 natural-language queries with known-correct answers, scored
**hit@1** (top result correct) and **hit@5** (correct answer in top 5), judged by
declaration-name match. Small and strict — treat as a directional gauge, not a
benchmark.

| Configuration | hit@1 | hit@5 |
|---------------|:-----:|:-----:|
| Dense only (MiniLM, torch) | 26% | 66% |
| **Dense + lexical RRF** (torch MiniLM) | **40%** | **80%** |
| Dense + lexical RRF (fastembed MiniLM — prod) | 33% | 60% |
| Equal-weight dense+sparse fusion | 26% | 53% |
| Cross-encoder rerank (ms-marco MiniLM) | regressed | regressed |

Takeaways:
- **Corpus coverage dominates.** Before pulling the full `rocq-prover/stdlib`
  (stdlib went 1.4k → 13.7k declarations), list/arith queries were unanswerable.
  No ranking trick beats having the data.
- **Lexical reorder is a real, safe win** (+14pp over dense-only). It ships on.
- **fastembed's ONNX MiniLM ranks a bit below torch MiniLM** (60 vs 80 hit@5) —
  accepted as the price of fitting the memory budget.

---

## 6. What was tried and rejected (and why)

Honesty matters more here than a clean story:

- **Cross-encoder reranking** (the textbook "biggest win") **regressed** quality:
  generic cross-encoders are trained on natural-language web text and score terse
  Coq declarations near-zero, scrambling correct dense hits. Kept as opt-in
  (`ROQET_RERANK=cross`), off by default.
- **Equal-weight BM25 + dense fusion** scored *worse* than dense+lexical (hit@5
  53% vs 80%). On prose queries the BM25 side injects keyword-matchy but wrong
  candidates (`add_assoc` for "commutative", `aa4` for "two plus two") that
  outvote correct dense hits. The sparse index is still built, and `fusion` mode
  is available for future **weighted** tuning — but equal weight is not the default.

The lesson: for this domain, dense should *retrieve* and lexical should only
*reorder*; keyword signal as an equal retriever hurts.

---

## 7. Known failure modes

Observed across ~25 exploratory queries:

1. **Variant-family bias.** "zero is the identity for addition" surfaces
   `Qplus_0_l` (rationals) over the core `add_0_l`; there are many near-identical
   `Q`/`Qc`/`Z`/`Pos` cousins and the embedder clusters them, so the *canonical*
   lemma loses. The most common imperfection.
2. **Abstract logic principles** with weak textual signal miss: "false implies
   anything" doesn't surface `False_rect`; "double negation" misses `NNPP`.
3. **Compound-name over-reward** from the lexical pass: "length of a mapped list"
   can rank `flat_map_constant_length` over the exact `length_map`.
4. **Relational precision is soft**: "membership in a concatenated list" returns
   `length_concat` rather than `in_app`.

Most trace back to the same root: terse names + thin/auto docstrings.

---

## 8. Tuning knobs

| Variable | Default | Effect |
|----------|---------|--------|
| `ROQET_EMBEDDER` | `hash` | Dense model (must match index). Prod: `fastembed`. |
| `ROQET_SEARCH` | `dense` | `dense` retrieval, or `fusion` (dense+BM25 RRF). |
| `ROQET_RERANK` | `auto` | `auto`/`lexical`, `cross`, or `off`. |
| `ROQET_RERANK_CANDIDATES` | `40` | Candidate pool size before rerank. |
| `ROQET_RRF_K` | `60` | RRF constant (higher = flatter rank weighting). |

---

## 9. Highest-leverage next steps

Ordered by expected impact, **no LLM required**:

1. **Stronger embedding model + query/passage prefixes** (e.g. `bge-base`/`bge-small`)
   — the most promising untried lever; MiniLM is small and we don't use instruction prefixes.
2. **Weighted (dense-favoring) fusion** — recover BM25 recall for identifier
   queries without the equal-weight regression.
3. **Cleaner / richer indexed text** — replace restate-the-signature docstrings;
   directly attacks failure modes 1–4.
4. **Canonical-form boosting** — prefer core modules / shorter canonical names so
   the "famous" lemma wins ties (variant-family bias).
5. **Type-aware / structural search** via coq-lsp/SerAPI — the research-grade leap:
   match by elaborated type shape (`?a + ?b = ?b + ?a`), not just text.

A small fixed evaluation set is the prerequisite to tune any of these with numbers
instead of vibes.
