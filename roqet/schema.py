"""Shared declaration schema helpers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


GITHUB_BASES = {
    "stdlib": "https://github.com/rocq-prover/stdlib/blob/master/theories",
    "coq": "https://github.com/coq/coq/blob/master/theories",
    "mathcomp": "https://github.com/math-comp/math-comp/blob/master",
    "unimath": "https://github.com/UniMath/UniMath/blob/master/UniMath",
    "hott": "https://github.com/HoTT/Coq-HoTT/blob/master/theories",
    "iris": "https://gitlab.mpi-sws.org/iris/iris/-/blob/master",
    "geocoq": "https://github.com/GeoCoq/GeoCoq/blob/master/theories",
    "mathcomp-analysis": "https://github.com/math-comp/analysis/blob/master",

}

# Matches a GeoCoq chapter token in a file path, e.g. "Main/Tarski_dev/Ch12_parallel.v".
_CHAPTER_RE = re.compile(r"(Ch\d{1,2})")

KNOWN_SUBDIRS = {
    "stdlib": "theories",
    "coq": "theories",
    "unimath": "UniMath",
    "hott": "theories",
}


def compact_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def stable_id(declaration: dict[str, Any]) -> int:
    key = canonical_key(declaration)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def canonical_key(declaration: dict[str, Any]) -> str:
    d = normalize_declaration(declaration)
    return f"{d['library']}:{d['file_path']}:{d['line_number']}:{d['name']}"


def make_github_url(library: str, file_path: str, line_number: int) -> str:
    base = GITHUB_BASES.get(library, "")
    if not base:
        return ""

    rel = Path(file_path).as_posix()
    subdir = KNOWN_SUBDIRS.get(library)
    if subdir:
        rel = re.sub(rf"^{re.escape(subdir)}/", "", rel)
    return f"{base}/{rel}#L{line_number}"


def normalize_declaration(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical declaration shape used by indexing and the API.

    Phase 1 had two prototype schemas. This accepts both:
    `type/doc/module/file/line` and
    `type_signature/docstring/module_path/file_path/line_number`.
    """
    library = str(raw.get("library") or "unknown")
    file_path = str(raw.get("file_path") or raw.get("file") or "")
    line_number = int(raw.get("line_number") or raw.get("line") or 0)
    github_url = str(raw.get("github_url") or "")
    if not github_url and file_path and line_number:
        github_url = make_github_url(library, file_path, line_number)
    chapter = str(raw.get("chapter") or derive_chapter(file_path))

    return {
        "name": str(raw.get("name") or ""),
        "kind": str(raw.get("kind") or ""),
        "type_signature": compact_ws(str(raw.get("type_signature") or raw.get("type") or "")),
        "statement": compact_ws(str(raw.get("statement") or "")),
        "docstring": compact_ws(str(raw.get("docstring") or raw.get("doc") or "")),
        "nl_description": compact_ws(str(raw.get("nl_description") or "")),
        "module_path": str(raw.get("module_path") or raw.get("module") or ""),
        "library": library,
        "file_path": file_path,
        "line_number": line_number,
        "github_url": github_url,
        "chapter": chapter,
    }


def derive_chapter(file_path: str) -> str:
    """GeoCoq Tarski_dev files are named ChNN_*.v; surface that as a filterable
    'chapter' (e.g. 'Ch12'). Empty for paths without a chapter token."""
    match = _CHAPTER_RE.search(file_path or "")
    return match.group(1) if match else ""


def declaration_text(raw: dict[str, Any]) -> str:
    d = normalize_declaration(raw)
    parts = [
        d.get("nl_description", ""),
        f"{d['kind']} {d['name']}",
        d["type_signature"],
        d["docstring"],
        d["statement"],
        f"module {d['module_path']}" if d["module_path"] else "",
        f"library {d['library']}",
    ]
    return " | ".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# Sparse (BM25-style) text vectors for hybrid search.
#
# We tokenize the declaration text (splitting snake_case and CamelCase
# identifiers) and hash each token to a stable sparse-vector index. Values are
# raw term frequencies; Qdrant applies IDF weighting at query time (the sparse
# collection is created with Modifier.IDF), giving BM25-like keyword scoring
# without any external vocabulary or model.
# ---------------------------------------------------------------------------

_SP_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_SP_CAMEL_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def sparse_tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in _SP_TOKEN_RE.findall(text or ""):
        low = raw.lower()
        if len(low) >= 2:
            out.append(low)
        for part in _SP_CAMEL_RE.findall(raw):
            pl = part.lower()
            if len(pl) >= 2 and pl != low:
                out.append(pl)
    return out


def token_id(token: str) -> int:
    return int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % (2**31)


def sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """Return (indices, values) term-frequency sparse vector for `text`."""
    from collections import Counter

    counts = Counter(token_id(t) for t in sparse_tokens(text))
    return list(counts.keys()), [float(v) for v in counts.values()]


def sparse_text(raw: dict[str, Any]) -> str:
    """The fields a keyword search should match against."""
    d = normalize_declaration(raw)
    return " ".join(p for p in (d["name"], d["type_signature"], d["statement"], d["docstring"]) if p)
