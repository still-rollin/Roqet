"""Shared declaration schema helpers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


GITHUB_BASES = {
    "stdlib": "https://github.com/rocq-prover/rocq/blob/master/theories",
    "coq": "https://github.com/coq/coq/blob/master/theories",
    "mathcomp": "https://github.com/math-comp/math-comp/blob/master",
    "unimath": "https://github.com/UniMath/UniMath/blob/master/UniMath",
    "hott": "https://github.com/HoTT/Coq-HoTT/blob/master/theories",
    "iris": "https://gitlab.mpi-sws.org/iris/iris/-/blob/master",
}

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

    return {
        "name": str(raw.get("name") or ""),
        "kind": str(raw.get("kind") or ""),
        "type_signature": compact_ws(str(raw.get("type_signature") or raw.get("type") or "")),
        "statement": compact_ws(str(raw.get("statement") or "")),
        "docstring": compact_ws(str(raw.get("docstring") or raw.get("doc") or "")),
        "module_path": str(raw.get("module_path") or raw.get("module") or ""),
        "library": library,
        "file_path": file_path,
        "line_number": line_number,
        "github_url": github_url,
    }


def declaration_text(raw: dict[str, Any]) -> str:
    d = normalize_declaration(raw)
    parts = [
        f"{d['kind']} {d['name']}",
        d["type_signature"],
        d["docstring"],
        d["statement"],
        f"module {d['module_path']}" if d["module_path"] else "",
        f"library {d['library']}",
    ]
    return " | ".join(part for part in parts if part)
