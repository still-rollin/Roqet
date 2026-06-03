"""FastAPI search service for Roqet."""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from roqet.embedder import COLLECTION_NAME, get_client, make_embedder

DEFAULT_LIMIT = 10
MAX_LIMIT = 50

app = FastAPI(
    title="Roqet API",
    description="Semantic search over Rocq/Coq mathematical libraries",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_embedder = None
_client = None


class SearchResult(BaseModel):
    name: str
    kind: str
    type_signature: str
    statement: str = ""
    docstring: str = ""
    module_path: str = ""
    library: str
    file_path: str
    line_number: int
    github_url: str = ""
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    elapsed_ms: float


class StatsResponse(BaseModel):
    total_points: int
    libraries: dict[str, int]
    kinds: dict[str, int]


def embedder():
    global _embedder
    if _embedder is None:
        _embedder = make_embedder(os.environ.get("ROQET_EMBEDDER", "hash"))
    return _embedder


def client():
    global _client
    if _client is None:
        _client = get_client(os.environ.get("QDRANT_URL") or None)
    return _client


def build_filter(lib: str | None, kind: str | None):
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    conditions = []
    lib = lib if isinstance(lib, str) else None
    kind = kind if isinstance(kind, str) else None
    if lib:
        conditions.append(FieldCondition(key="library", match=MatchAny(any=[x.strip() for x in lib.split(",") if x.strip()])))
    if kind:
        conditions.append(FieldCondition(key="kind", match=MatchAny(any=[x.strip() for x in kind.split(",") if x.strip()])))
    return Filter(must=conditions) if conditions else None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "collection": COLLECTION_NAME}


@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    lib: str | None = Query(None),
    kind: str | None = Query(None),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    started = time.time()
    vector = embedder().embed([q])[0]
    try:
        hits = query_points(vector=vector, query_filter=build_filter(lib, kind), limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search index unavailable: {exc}") from exc

    results = []
    for hit in hits:
        payload: dict[str, Any] = hit.payload or {}
        results.append(SearchResult(**payload, score=round(float(hit.score), 4)))

    return SearchResponse(
        query=q,
        results=results,
        total=len(results),
        elapsed_ms=round((time.time() - started) * 1000, 1),
    )


@app.get("/libs")
def libs() -> dict[str, dict[str, int]]:
    return {"libraries": scroll_counts("library")}


@app.get("/stats", response_model=StatsResponse)
def stats():
    try:
        info = client().get_collection(COLLECTION_NAME)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search index unavailable: {exc}") from exc
    return StatsResponse(
        total_points=info.points_count or 0,
        libraries=scroll_counts("library"),
        kinds=scroll_counts("kind"),
    )


def scroll_counts(field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    offset = None
    while True:
        points, offset = client().scroll(
            collection_name=COLLECTION_NAME,
            limit=1000,
            offset=offset,
            with_payload=[field],
            with_vectors=False,
        )
        for point in points:
            value = (point.payload or {}).get(field, "unknown")
            counts[value] = counts.get(value, 0) + 1
        if offset is None:
            return dict(sorted(counts.items()))


def query_points(vector: list[float], query_filter, limit: int):
    qdrant = client()
    if hasattr(qdrant, "query_points"):
        result = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return result.points

    return qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
