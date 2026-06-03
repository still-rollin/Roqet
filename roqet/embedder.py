"""Embed declarations and index them into Qdrant."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Protocol

from roqet.schema import declaration_text, normalize_declaration, stable_id

COLLECTION_NAME = os.environ.get("ROQET_COLLECTION", "roqet_declarations")
BATCH_SIZE = int(os.environ.get("ROQET_BATCH_SIZE", "64"))
QDRANT_PATH = os.environ.get("QDRANT_PATH", "data/qdrant_storage")
DEFAULT_LOCAL_MODEL = os.environ.get("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
# Hard cap on tokens fed to the transformer. Some declarations (large records,
# generated terms) are enormous; without truncation a transformer's O(n^2)
# attention can try to allocate absurd buffers. 512 is plenty for a declaration.
MAX_SEQ_LENGTH = int(os.environ.get("EMBED_MAX_SEQ_LENGTH", "512"))
OPENAI_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")
HASH_DIM = 384


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashEmbedder:
    """Tiny deterministic embedder for smoke tests and offline demos."""

    dim = HASH_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().replace("_", " ").split():
            bucket = stable_token_bucket(token, self.dim)
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def stable_token_bucket(token: str, dim: int) -> int:
    import hashlib

    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dim


class LocalEmbedder:
    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, trust_remote_code=True)
        # Force truncation so a pathologically long declaration can't blow up
        # the transformer's attention buffers.
        current = self.model.max_seq_length or MAX_SEQ_LENGTH
        self.model.max_seq_length = min(current, MAX_SEQ_LENGTH)
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()


class OpenAIEmbedder:
    def __init__(self, model_name: str = OPENAI_MODEL):
        from openai import OpenAI

        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model_name
        self.dim = 1536 if model_name.endswith("small") else 3072

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in resp.data]


def make_embedder(kind: str) -> Embedder:
    if kind == "hash":
        return HashEmbedder()
    if kind == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for --model openai")
        return OpenAIEmbedder()
    return LocalEmbedder()


def get_client(url: str | None = None):
    from qdrant_client import QdrantClient

    api_key = os.environ.get("QDRANT_API_KEY") or None
    if url:
        return QdrantClient(url=url, api_key=api_key)
    return QdrantClient(path=QDRANT_PATH)


def setup_collection(client, dim: int, reset: bool = False) -> None:
    from qdrant_client.models import Distance, VectorParams

    exists = any(c.name == COLLECTION_NAME for c in client.get_collections().collections)
    if exists and reset:
        client.delete_collection(COLLECTION_NAME)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def load_declarations(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [normalize_declaration(json.loads(line)) for line in fh if line.strip()]


def existing_keys(client) -> set[str]:
    keys: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1000,
            offset=offset,
            with_payload=["library", "file_path", "line_number", "name"],
            with_vectors=False,
        )
        for point in points:
            if point.payload:
                keys.add(
                    f"{point.payload.get('library')}:{point.payload.get('file_path')}:"
                    f"{point.payload.get('line_number')}:{point.payload.get('name')}"
                )
        if offset is None:
            return keys


def index_declarations(decls: list[dict], embedder: Embedder, client, resume: bool = True) -> int:
    from qdrant_client.models import PointStruct

    already = existing_keys(client) if resume else set()
    pending = [d for d in decls if f"{d['library']}:{d['file_path']}:{d['line_number']}:{d['name']}" not in already]
    started = time.time()
    indexed = 0

    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        texts = [declaration_text(d) for d in batch]
        vectors = embedder.embed(texts)
        points = [
            PointStruct(
                id=stable_id(decl),
                vector=vector,
                payload={**decl, "search_text": text},
            )
            for decl, vector, text in zip(batch, vectors, texts)
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        indexed += len(points)
        elapsed = max(time.time() - started, 0.001)
        print(f"[{indexed}/{len(pending)}] {indexed / elapsed:.0f} decls/s")

    return indexed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/declarations.jsonl"))
    parser.add_argument("--model", choices=["hash", "local", "openai"], default="hash")
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL") or None)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input.exists():
        raise SystemExit(f"Input not found: {args.input}")

    embedder = make_embedder(args.model)
    client = get_client(args.qdrant_url)
    setup_collection(client, embedder.dim, reset=args.reset)
    declarations = load_declarations(args.input)
    indexed = index_declarations(declarations, embedder, client, resume=not args.no_resume)
    info = client.get_collection(COLLECTION_NAME)
    print(f"Indexed {indexed} new declarations. Collection has {info.points_count} points.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
