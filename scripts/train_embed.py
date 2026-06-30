"""Fine-tune a Rocq-specific embedding model (rocqet-embed).

Contrastive fine-tune of all-MiniLM-L6-v2 (384-d, the model we already serve via
fastembed) on the MathComp (description -> declaration) pairs + structural hard
negatives produced by ``python -m rocqet.finetune``. Goal: close the *discrimination*
gap that descriptions alone leave — teach the model to encode the relation
(``same_env`` vs ``same_env_sym``), not just the dominant noun — so the exact lemma
ranks #1, not merely the right neighborhood.

Loss: MultipleNegativesRankingLoss. Each anchor (NL description) is pulled toward
its declaration and pushed away from (a) the explicit hard negatives — same-concept,
different-relation siblings — and (b) the rest of the batch (in-batch negatives).

Runs on a free Colab T4 in ~10-30 min. Locally it works too (CPU = slow).

    # in Colab: upload data/finetune/train.jsonl, then
    pip install -U sentence-transformers
    python scripts/train_embed.py --train train.jsonl --out rocqet-embed --epochs 1

Export the result to ONNX for fastembed serving with --onnx (see scripts/export_onnx.py).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_triplets(path: Path) -> list[dict]:
    """One (anchor, positive, negative) row per hard negative. Rows without a hard
    negative fall back to (anchor, positive) — MNRL still uses in-batch negatives."""
    triplets, pairs = [], []
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        anchor, pos, negs = r["query"], r["positive"], r.get("negatives") or []
        if not anchor or not pos:
            continue
        if negs:
            for n in negs:
                triplets.append({"anchor": anchor, "positive": pos, "negative": n})
        else:
            pairs.append({"anchor": anchor, "positive": pos})
    return triplets, pairs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", type=Path, default=Path("data/finetune/train.jsonl"))
    ap.add_argument("--base", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--out", type=Path, default=Path("models/rocqet-embed"))
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-pairs-only", type=int, default=0,
                    help="cap the no-hard-negative pair rows added (0 = drop them)")
    args = ap.parse_args(argv)

    from datasets import Dataset
    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )
    from sentence_transformers.losses import MultipleNegativesRankingLoss

    triplets, pairs = load_triplets(args.train)
    print(f"triplets (with hard neg): {len(triplets):,} | pair-only: {len(pairs):,}")

    # MNRL needs one consistent schema per dataset; train on the hard-negative triplets
    # (they carry the discrimination signal). Optionally mix in some pair-only rows.
    rows = list(triplets)
    if args.max_pairs_only and pairs:
        rows += [{"anchor": p["anchor"], "positive": p["positive"], "negative": ""}
                 for p in pairs[: args.max_pairs_only]]
    # drop empty-negative rows if any slipped in (keep a clean triplet schema)
    rows = [r for r in rows if r.get("negative")]
    ds = Dataset.from_list(rows)
    print(f"training rows: {len(ds):,}")

    model = SentenceTransformer(args.base)
    loss = MultipleNegativesRankingLoss(model)

    targs = SentenceTransformerTrainingArguments(
        output_dir=str(args.out / "_ckpt"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        fp16=True,                     # T4-friendly; ignored on CPU
        dataloader_drop_last=True,     # stable in-batch negatives
        logging_steps=50,
        save_strategy="no",
        report_to=[],
    )
    trainer = SentenceTransformerTrainer(model=model, args=targs, train_dataset=ds, loss=loss)
    trainer.train()

    args.out.mkdir(parents=True, exist_ok=True)
    model.save(str(args.out))
    print(f"\nsaved fine-tuned model -> {args.out}")
    print("next: export to ONNX (scripts/export_onnx.py) and serve via fastembed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
