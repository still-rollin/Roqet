"""Roqet MCP server.

Exposes Roqet's semantic search over Rocq/Coq libraries as MCP tools, so an LLM
agent (Claude, etc.) can discover lemmas/definitions by *meaning* — the semantic
layer the Rocq MCP ecosystem otherwise lacks. It complements proof-loop servers
like rocq-mcp (which wrap `coqc`'s exact/keyword `Search`).

This is a thin client: it calls a running Roqet HTTP API (local or hosted). Point
it at the API with the ROQET_API_URL environment variable.

    ROQET_API_URL=https://your-roqet.up.railway.app roqet-mcp

Run locally (stdio transport, for Claude Desktop / Claude Code):

    roqet-mcp
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("ROQET_API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = float(os.environ.get("ROQET_MCP_TIMEOUT", "30"))

mcp = FastMCP("roqet")


def _get(path: str, params: dict | None = None) -> dict:
    resp = httpx.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _format_result(r: dict) -> str:
    lines = [f"### {r.get('kind', '')} {r.get('name', '')}  ({r.get('library', '')})  score={r.get('score')}"]
    if r.get("type_signature"):
        lines.append(f"    : {r['type_signature']}")
    if r.get("statement"):
        lines.append(f"    {r['statement']}")
    if r.get("docstring"):
        lines.append(f"    — {r['docstring']}")
    loc = r.get("github_url") or f"{r.get('file_path', '')}:{r.get('line_number', '')}"
    if loc:
        lines.append(f"    {loc}")
    return "\n".join(lines)


@mcp.tool()
def roqet_search(query: str, lib: str = "", kind: str = "", limit: int = 10) -> str:
    """Semantically search Rocq/Coq library declarations by meaning.

    Use this to find a lemma, theorem, or definition when you can describe what it
    says but don't know its exact name — e.g. "addition on naturals is commutative"
    or "the empty set has no elements". Unlike exact/keyword search, matches need
    not share literal words with your query.

    Args:
        query: Natural-language description of what you're looking for.
        lib: Optional library filter. Comma-separated for several (e.g. "stdlib,mathcomp").
        kind: Optional kind filter, e.g. "Lemma" or "Lemma,Theorem,Definition".
        limit: Max results to return (1-50).

    Returns:
        A formatted list of matching declarations with type signatures, statements,
        and source links.
    """
    try:
        params: dict = {"q": query, "limit": max(1, min(int(limit), 50))}
        if lib.strip():
            params["lib"] = lib.strip()
        if kind.strip():
            params["kind"] = kind.strip()
        data = _get("/search", params)
    except httpx.HTTPError as exc:
        return (
            f"Could not reach the Roqet API at {API_BASE} ({exc}). "
            "Is it running? Set ROQET_API_URL to the correct base URL."
        )

    results = data.get("results", [])
    if not results:
        return f"No declarations found for {query!r}."
    header = f"{len(results)} result(s) for {query!r} ({data.get('elapsed_ms', '?')} ms):"
    return header + "\n\n" + "\n\n".join(_format_result(r) for r in results)


@mcp.tool()
def roqet_stats() -> str:
    """Report what the Roqet index currently contains.

    Returns the total number of indexed declarations and the per-library and
    per-kind breakdown — useful for knowing what corpus is searchable before querying.
    """
    try:
        data = _get("/stats")
    except httpx.HTTPError as exc:
        return f"Could not reach the Roqet API at {API_BASE} ({exc}). Set ROQET_API_URL."
    libs = ", ".join(f"{k}: {v}" for k, v in sorted(data.get("libraries", {}).items()))
    kinds = ", ".join(f"{k}: {v}" for k, v in sorted(data.get("kinds", {}).items()))
    return (
        f"Roqet index ({API_BASE}): {data.get('total_points', 0)} declarations\n"
        f"Libraries: {libs or '(none)'}\n"
        f"Kinds: {kinds or '(none)'}"
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
