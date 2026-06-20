"""FastAPI search service for Rocqet."""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rocqet import rerank
from rocqet.embedder import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    get_client,
    make_embedder,
)
from rocqet.schema import sparse_vector

DEFAULT_LIMIT = 10
MAX_LIMIT = 50

app = FastAPI(
    title="Rocqet API",
    description="Semantic search over Rocq/Coq mathematical libraries",
    version="0.1.0",
)
# Public, read-only search API: default to permissive CORS so any client (the
# UI, MCP servers, notebooks) can call it. Restrict to specific origins in
# production by setting CORS_ORIGINS (comma-separated). Only GET is exposed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

_embedder = None
_client = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rocqet")

# Simple in-memory per-IP sliding-window rate limit (ROCQET_RATE_LIMIT=0 disables).
# Fine for a single-instance deployment; protects the Qdrant quota from abuse.
RATE_LIMIT = int(os.environ.get("ROCQET_RATE_LIMIT", "60"))  # requests/min/IP
RATE_WINDOW = 60.0
_hits: dict[str, deque] = {}


def enforce_rate_limit(request: Request) -> None:
    if RATE_LIMIT <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    dq = _hits.setdefault(ip, deque())
    while dq and now - dq[0] > RATE_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")
    dq.append(now)
    if len(_hits) > 10000:  # bound memory: drop IPs with no recent hits
        for k in [k for k, v in _hits.items() if not v]:
            _hits.pop(k, None)


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
    chapter: str = ""
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
        _embedder = make_embedder(os.environ.get("ROCQET_EMBEDDER", "hash"))
    return _embedder


def client():
    global _client
    if _client is None:
        _client = get_client(os.environ.get("QDRANT_URL") or None)
    return _client


def build_filter(lib: str | None, kind: str | None, chapter: str | None = None):
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    conditions = []
    for key, value in (("library", lib), ("kind", kind), ("chapter", chapter)):
        if isinstance(value, str) and value.strip():
            terms = [x.strip() for x in value.split(",") if x.strip()]
            conditions.append(FieldCondition(key=key, match=MatchAny(any=terms)))
    return Filter(must=conditions) if conditions else None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "collection": COLLECTION_NAME}


@app.get("/search", response_model=SearchResponse)
def search(
    request: Request,
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    lib: str | None = Query(None),
    kind: str | None = Query(None),
    chapter: str | None = Query(None, description="GeoCoq chapter filter, e.g. Ch12"),
):
    enforce_rate_limit(request)
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    started = time.time()
    vector = embedder().embed([q])[0]
    try:
        hits = query_points(
            query=q,
            vector=vector,
            query_filter=build_filter(lib, kind, chapter),
            limit=rerank.candidate_pool(limit),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search index unavailable: {exc}") from exc

    # Hybrid fusion already blends semantic + keyword. The optional cross-encoder
    # reranker can still reorder the fused candidates when explicitly enabled.
    scored = rerank.rerank(q, hits, limit)

    results = []
    for hit, score in scored:
        payload: dict[str, Any] = hit.payload or {}
        results.append(SearchResult(**payload, score=round(float(score), 4)))

    elapsed_ms = round((time.time() - started) * 1000, 1)
    logger.info("search q=%r lib=%s kind=%s results=%d ms=%.1f", q, lib, kind, len(results), elapsed_ms)

    return SearchResponse(
        query=q,
        results=results,
        total=len(results),
        elapsed_ms=elapsed_ms,
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


SEARCH_MODE = os.environ.get("ROCQET_SEARCH", "dense").strip().lower()


def query_points(query: str, vector: list[float], query_filter, limit: int):
    """Retrieve candidates.

    Default: dense (semantic) retrieval over the named dense vector — measured best
    on natural-language queries, with lexical reordering applied afterwards by
    `rerank`. Opt-in `ROCQET_SEARCH=fusion` blends dense + BM25 sparse with RRF
    (better recall for identifier queries, but noisier on prose queries).
    """
    qdrant = client()

    if SEARCH_MODE == "fusion":
        from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

        sp_idx, sp_val = sparse_vector(query)
        prefetch_n = max(limit, 40)
        result = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                Prefetch(query=vector, using=DENSE_VECTOR_NAME, limit=prefetch_n, filter=query_filter),
                Prefetch(
                    query=SparseVector(indices=sp_idx, values=sp_val),
                    using=SPARSE_VECTOR_NAME,
                    limit=prefetch_n,
                    filter=query_filter,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return result.points

    result = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        using=DENSE_VECTOR_NAME,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    return result.points
