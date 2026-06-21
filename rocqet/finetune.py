"""Build contrastive training data for a Rocq-specific embedding model.

Turns ``declarations.enriched.jsonl`` into ``(query, positive, hard_negatives)``
triples with a *leakage-safe*, cluster-based train/test split. Pure Python — no
GPU, no LLM at this stage.

The design in one paragraph:

* **positive** = the lemma's document text (NL description + name + type +
  statement); the **query** is its natural-language description (or a synthetic
  fallback when none exists yet).
* **hard negatives** = the secret sauce. For a lemma we mine *same concept,
  different relation* siblings — declarations that share the name/type **stem**
  (the noun, e.g. ``cong``) but differ in the **relation** (``transitivity`` vs
  ``symmetry``), plus the ``characterization_of_*`` / ``postulate_of_*`` look-
  alikes that currently dominate. These are exactly the cases a generic embedder
  confuses, so training to separate them is where the large gain comes from.
* **leakage-safe split** = we split by *near-duplicate cluster* (lemmas with the
  same variable-normalized statement, e.g. ``cong_sym`` ≡ ``cong_symmetry``), not
  by individual lemma, so the test set never contains a twin of a training item.

    python -m rocqet.finetune --input deploy/declarations.enriched.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from rocqet.schema import declaration_text, normalize_declaration, sparse_tokens

# Tokens that denote the *relation/property* a lemma asserts. Two same-stem
# declarations whose relation tokens differ are ideal hard negatives: same noun,
# different meaning — the distinction generic embedders miss.
RELATION_TOKENS = {
    "sym", "symmetry", "symmetric", "trans", "transitivity", "transitive",
    "refl", "reflexivity", "reflexive", "irreflexive", "comm", "commutativity",
    "commutative", "assoc", "associativity", "associative", "dec", "decidable",
    "decidability", "antisym", "antisymmetry", "inj", "injective", "surj",
    "surjective", "mono", "monotone", "monotonicity", "idempotent", "distributive",
    "cancel", "unique", "uniqueness", "exists", "existence", "trivial", "id",
    "identity", "inverse", "involutive", "preserves", "compat", "congr",
}

# Generic "noise" tokens that shouldn't anchor a concept stem.
_STOP = {"of", "the", "a", "an", "is", "to", "and", "or", "in", "by", "for",
         "lemma", "theorem", "def", "definition", "bis", "aux", "alt"}

_VAR_RE = re.compile(r"\b[A-Z][0-9']?\b")        # point/variable names: A, B, C, A1, A'
_WS_RE = re.compile(r"\s+")


def name_tokens(decl: dict) -> list[str]:
    """snake_case + CamelCase tokens of the declaration name, lowercased."""
    return sparse_tokens(decl.get("name", ""))


def concept_stem(decl: dict) -> str:
    """The grouping key for hard-negative mining: the leading *noun* token of the
    name, ignoring relation/digit/noise tokens. e.g. cong_transitivity -> 'cong',
    col_permutation_1 -> 'col', perp_sym -> 'perp'. Empty if nothing usable."""
    for tok in name_tokens(decl):
        if tok in RELATION_TOKENS or tok in _STOP or tok.isdigit() or len(tok) < 2:
            continue
        return tok
    return ""


def relation_signature(decl: dict) -> frozenset[str]:
    """The set of relation tokens in the name (e.g. {'transitivity'})."""
    return frozenset(t for t in name_tokens(decl) if t in RELATION_TOKENS)


def cluster_key(decl: dict) -> str:
    """Near-duplicate cluster for leakage-safe splitting. Two lemmas with the same
    variable-normalized statement (e.g. cong_sym and cong_symmetry, both
    ``Cong A B C D -> Cong C D A B``) land in the same cluster, so a train/test
    split by cluster never leaks a twin across the boundary."""
    body = decl.get("statement") or decl.get("type_signature") or decl.get("name", "")
    body = re.sub(r"^\s*\w+\s+\w+\s*:", "", body)          # drop "Lemma name :"
    body = _VAR_RE.sub("_", body)                          # erase variable names
    body = _WS_RE.sub(" ", body).strip().lower()
    return f"{decl.get('library', '')}::{body}" if body else f"name::{decl.get('name', '')}"


def make_query(decl: dict) -> tuple[str, bool]:
    """The NL query side. Real description if present, else a synthetic fallback
    from the name tokens. Returns (query, is_real)."""
    desc = (decl.get("nl_description") or "").strip()
    if desc:
        return desc, True
    toks = [t for t in name_tokens(decl) if not t.isdigit()]
    return (" ".join(toks) or decl.get("name", "")), False


def is_lookalike(decl: dict, stem: str) -> bool:
    """The 'characterization_of_X' / 'postulate_of_X' family that currently buries
    the canonical lemma — always a good hard negative for concept `stem`."""
    name = decl.get("name", "").lower()
    return ("characterization" in name or "postulate" in name) and stem and stem in name


def mine_hard_negatives(decl, by_stem, lookalikes, k=5) -> list[dict]:
    """Same concept, different relation. Candidates are (a) same-stem/same-library
    siblings and (b) the characterization_of_<stem> / postulate_of_<stem> look-
    alikes (which live under a different stem, so we inject them explicitly). All
    must sit in a *different* near-duplicate cluster than `decl`. Ranking, best
    first: the look-alike dominators, then a *different explicit relation* (the
    cong_sym-vs-cong_transitivity teaching case), then structural siblings, then
    same-relation lemmas (likely near-equivalents — weakest)."""
    stem = concept_stem(decl)
    if not stem:
        return []
    my_cluster = cluster_key(decl)
    my_rel = relation_signature(decl)
    look = [c for c in lookalikes
            if c["library"] == decl["library"] and stem in c["name"].lower()]
    cands = {c["name"]: c for c in by_stem.get((decl["library"], stem), []) + look
             if cluster_key(c) != my_cluster and c["name"] != decl["name"]}.values()

    def rank(c):
        rel = relation_signature(c)
        if is_lookalike(c, stem):
            return 0                       # the measured dominators — top priority
        if rel and rel != my_rel:
            return 1                       # same noun, different relation — the teacher
        if not rel:
            return 2                       # structural sibling
        return 3                           # same relation — possible near-equivalent
    return sorted(cands, key=rank)[:k]


def split_is_test(decl: dict, test_frac: float) -> bool:
    """Deterministic split by cluster hash (no RNG → reproducible)."""
    h = hashlib.sha256(cluster_key(decl).encode()).hexdigest()
    return (int(h[:8], 16) % 1000) < int(test_frac * 1000)


def build(records: list[dict], k: int, test_frac: float):
    decls = [normalize_declaration(r) for r in records]
    # Index by (library, stem) for negative mining; collect look-alikes separately
    # (their stem is "characterization"/"postulate", so they need explicit injection).
    by_stem: dict[tuple, list[dict]] = {}
    lookalikes: list[dict] = []
    for d in decls:
        stem = concept_stem(d)
        if stem:
            by_stem.setdefault((d["library"], stem), []).append(d)
        nm = d["name"].lower()
        if "characterization" in nm or "postulate" in nm:
            lookalikes.append(d)

    train, test, real_q = [], [], 0
    for d in decls:
        query, is_real = make_query(d)
        real_q += is_real
        negs = mine_hard_negatives(d, by_stem, lookalikes, k)
        # Keep negatives on the same side of the split as the anchor (no leakage).
        anchor_test = split_is_test(d, test_frac)
        negs = [n for n in negs if split_is_test(n, test_frac) == anchor_test]
        row = {
            "query": query,
            "positive": declaration_text(d),
            "negatives": [declaration_text(n) for n in negs],
            "name": d["name"], "library": d["library"],
            "neg_names": [n["name"] for n in negs], "real_query": is_real,
        }
        (test if anchor_test else train).append(row)
    return train, test, real_q


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=Path("deploy/declarations.enriched.jsonl"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/finetune"))
    ap.add_argument("--negatives", type=int, default=5)
    ap.add_argument("--test-frac", type=float, default=0.15)
    args = ap.parse_args(argv)

    records = [json.loads(line) for line in args.input.open(encoding="utf-8") if line.strip()]
    train, test, real_q = build(records, args.negatives, args.test_frac)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("test", test)):
        with (args.out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = len(train) + len(test)
    with_negs = sum(1 for r in train + test if r["negatives"])
    avg_negs = sum(len(r["negatives"]) for r in train + test) / max(with_negs, 1)
    print(f"records         : {total:,}")
    print(f"real NL queries : {real_q:,} ({real_q / max(total,1):.0%})  (rest synthetic fallback)")
    print(f"train / test    : {len(train):,} / {len(test):,}  (split by near-dup cluster)")
    print(f"with hard negs  : {with_negs:,} ({with_negs / max(total,1):.0%}), avg {avg_negs:.1f} negs each")
    print("\nexample triples (query  ->  positive  |  hard negatives):")
    shown = 0
    for r in train:
        if r["real_query"] and len(r["negatives"]) >= 3 and shown < 5:
            print(f"  Q: {r['query'][:70]}")
            print(f"     +  {r['name']}")
            print(f"     -  {', '.join(r['neg_names'][:5])}")
            shown += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
