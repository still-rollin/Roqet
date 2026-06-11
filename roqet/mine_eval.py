"""Mine a premise-selection evaluation set from Coq/Rocq proof scripts.

For each proved Lemma/Theorem/Corollary `T`, the declarations referenced in its
proof body are its *premises* — lemmas/definitions genuinely relevant to `T`'s
statement. Treating (statement of T) -> (premises of T) as (query -> relevant
set) gives a leakage-free, domain-native retrieval benchmark (the classic
*premise selection* task) mined directly from the .v sources, with no labeling.

Leakage-free because the proof body is NOT in the search index — the premises are
*other* declarations, so retrieving them is a genuine test, unlike querying a
lemma with its own indexed text.

Usage:
    python -m roqet.mine_eval \
        --enriched data/declarations.enriched.jsonl \
        --source repos/stdlib_full/theories=stdlib \
        --source repos/mathcomp=mathcomp \
        --source repos/geocoq/theories=geocoq \
        --out data/eval/premise_selection.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from roqet.extract import (
    DECLARATION_RE,
    extract_type,
    iter_statements,
    iter_v_files,
    parse_source,
    strip_comments_for_match,
)
from roqet.schema import compact_ws

# Kinds that carry a proof we can mine premises from.
PROOF_KINDS = {"Lemma", "Theorem", "Corollary", "Remark", "Fact", "Proposition"}

CLOSER_RE = re.compile(r"^\s*(Qed|Defined|Admitted|Abort)\b", re.IGNORECASE)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")

# Tactic/keyword tokens that are never premises (belt-and-suspenders; the real
# filter is membership in the corpus name set).
STOP = {
    "forall", "exists", "fun", "let", "in", "match", "with", "end", "if", "then",
    "else", "Type", "Prop", "Set", "by", "move", "apply", "rewrite", "exact",
    "intro", "intros", "destruct", "induction", "case", "split", "left", "right",
    "assumption", "reflexivity", "symmetry", "transitivity", "auto", "eauto",
    "simpl", "unfold", "Proof", "Qed", "Defined", "Admitted", "Abort", "as",
    "using", "have", "suff", "wlog", "pose", "set", "elim", "red", "cbn", "now",
    "trivial", "congruence", "lia", "ring", "field", "omega", "discriminate",
}


def proof_premises(body_segments: list[str], corpus_names: set[str], own_name: str) -> list[str]:
    toks: set[str] = set()
    for seg in body_segments:
        for raw in IDENT_RE.findall(seg):
            toks.add(raw)
            if "." in raw:
                toks.add(raw.rsplit(".", 1)[-1])  # last component of a qualified name
    return sorted(
        t for t in toks
        if t in corpus_names and t != own_name and len(t) >= 3 and t not in STOP
    )


def mine_file(path: Path, root, corpus_names: set[str]) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(root.path).as_posix()
    stmts = list(iter_statements(text))
    out: list[dict] = []
    i = 0
    while i < len(stmts):
        clean = strip_comments_for_match(stmts[i].text)
        match = DECLARATION_RE.match(clean)
        if not match or match.group("kind") not in PROOF_KINDS:
            i += 1
            continue
        name = match.group("name")

        # Collect the proof body: statements until a closer (Qed/Defined/...) or
        # the next declaration (a lemma with no parseable proof).
        j = i + 1
        body: list[str] = []
        closed = False
        while j < len(stmts):
            seg = strip_comments_for_match(stmts[j].text).strip()
            if CLOSER_RE.match(seg):
                closed = True
                j += 1
                break
            if DECLARATION_RE.match(seg):
                break
            body.append(seg)
            j += 1

        if closed and body:
            premises = proof_premises(body, corpus_names, name)
            if premises:
                out.append({
                    "name": name,
                    "kind": match.group("kind"),
                    "library": root.library,
                    "file_path": rel,
                    "type_signature": extract_type(match.group("rest").removesuffix(".")),
                    "statement": compact_ws(clean),
                    "premises": premises,
                })
        i = max(j, i + 1)
    return out


def load_corpus_names(path: Path) -> set[str]:
    names: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                names.add(json.loads(line).get("name", ""))
    names.discard("")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enriched", type=Path, default=Path("data/declarations.enriched.jsonl"),
                        help="Indexed corpus, used to keep only premises that are searchable.")
    parser.add_argument("--source", action="append", required=True, help="PATH=library, like roqet.extract")
    parser.add_argument("--out", type=Path, default=Path("data/eval/premise_selection.jsonl"))
    parser.add_argument("--min-premises", type=int, default=1)
    parser.add_argument("--max-premises", type=int, default=15,
                        help="Skip sprawling proofs; keep focused, gradeable queries.")
    parser.add_argument("--per-lib-cap", type=int, default=1500, help="Cap pairs per library.")
    args = parser.parse_args(argv)

    corpus_names = load_corpus_names(args.enriched)
    print(f"corpus names: {len(corpus_names):,}")

    by_lib: dict[str, list[dict]] = {}
    for value in args.source:
        root = parse_source(value)
        if not root.path.exists():
            raise FileNotFoundError(root.path)
        lib_pairs: list[dict] = []
        for vf in iter_v_files(root.path):
            for rec in mine_file(vf, root, corpus_names):
                if args.min_premises <= len(rec["premises"]) <= args.max_premises:
                    lib_pairs.append(rec)
        by_lib[root.library] = lib_pairs
        print(f"  {root.library}: mined {len(lib_pairs):,} usable pairs")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.out.open("w", encoding="utf-8") as out:
        for lib, pairs in by_lib.items():
            # Deterministic, balanced sample: evenly stride through the pairs.
            if len(pairs) > args.per_lib_cap:
                step = len(pairs) / args.per_lib_cap
                pairs = [pairs[int(k * step)] for k in range(args.per_lib_cap)]
            for rec in pairs:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total += 1
    print(f"Wrote {total:,} eval pairs to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
