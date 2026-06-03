"""Extract Rocq/Coq declarations from `.v` files.

This is a fast Phase 1 extractor. It does not typecheck files, but it handles
nested comments and statement boundaries well enough to build a first search
corpus from large libraries.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

from roqet.schema import make_github_url


DECLARATION_KINDS = (
    "Theorem",
    "Lemma",
    "Remark",
    "Fact",
    "Corollary",
    "Proposition",
    "Definition",
    "Let",
    "Fixpoint",
    "CoFixpoint",
    "Inductive",
    "CoInductive",
    "Record",
    "Structure",
    "Class",
    "Instance",
    "Program Definition",
    "Program Fixpoint",
    "Program Instance",
)

DECLARATION_RE = re.compile(
    r"^\s*(?:Local\s+|Global\s+|Polymorphic\s+|Monomorphic\s+|Canonical\s+)*"
    r"(?P<kind>"
    + "|".join(re.escape(kind) for kind in sorted(DECLARATION_KINDS, key=len, reverse=True))
    + r")\s+(?P<name>[A-Za-z_][A-Za-z0-9_']*)\b(?P<rest>.*)\.\s*$",
    re.DOTALL,
)

DOC_COMMENT_RE = re.compile(r"^\s*\(\*\*(?P<body>.*)\*\)\s*$", re.DOTALL)


@dataclass(frozen=True)
class SourceRoot:
    path: Path
    library: str


@dataclass(frozen=True)
class Statement:
    text: str
    leading_doc: str
    line: int


@dataclass(frozen=True)
class Declaration:
    name: str
    kind: str
    type_signature: str
    statement: str
    docstring: str
    module_path: str
    library: str
    file_path: str
    source_path: str
    line_number: int
    github_url: str


def parse_source(value: str) -> SourceRoot:
    """Parse `path=library` source arguments."""
    if "=" not in value:
        path = Path(value).expanduser().resolve()
        return SourceRoot(path=path, library=path.name)

    raw_path, library = value.rsplit("=", 1)
    path = Path(raw_path).expanduser().resolve()
    library = library.strip()
    if not library:
        raise ValueError(f"Missing library label in source: {value}")
    return SourceRoot(path=path, library=library)


def module_name(file_path: Path, root: Path) -> str:
    relative = file_path.relative_to(root).with_suffix("")
    return ".".join(relative.parts)


def clean_comment(text: str) -> str:
    match = DOC_COMMENT_RE.match(text)
    body = match.group("body") if match else text
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        lines.append(stripped)
    return " ".join(line for line in lines if line).strip()


def compact_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_type(rest: str) -> str:
    rest = compact_ws(rest)
    if not rest:
        return ""

    if rest.startswith(":"):
        return rest[1:].strip()
    if ":=" in rest:
        before, _sep, _after = rest.partition(":=")
        if ":" in before:
            return before.rsplit(":", 1)[1].strip()
        return ""
    return rest


def strip_comments_for_match(text: str) -> str:
    """Remove comments while preserving code outside comments."""
    out: list[str] = []
    i = 0
    depth = 0
    in_string = False
    while i < len(text):
        two = text[i : i + 2]
        if depth == 0 and text[i] == '"':
            out.append(text[i])
            i += 1
            in_string = not in_string
            continue
        if not in_string and two == "(*":
            depth += 1
            i += 2
            continue
        if not in_string and depth > 0 and two == "*)":
            depth -= 1
            i += 2
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return "".join(out)


def iter_statements(text: str) -> Iterator[Statement]:
    buffer: list[str] = []
    doc_buffer: list[str] = []
    statement_start_line = 1
    line = 1
    comment_depth = 0
    comment_buffer: list[str] = []
    in_string = False
    i = 0

    while i < len(text):
        char = text[i]
        two = text[i : i + 2]

        if char == "\n":
            line += 1

        if comment_depth == 0 and char == '"':
            in_string = not in_string
            buffer.append(char)
            i += 1
            continue

        if not in_string and two == "(*":
            if not buffer or not "".join(buffer).strip():
                statement_start_line = line
            comment_depth += 1
            comment_buffer.append(two)
            i += 2
            continue

        if not in_string and comment_depth > 0:
            if two == "(*":
                comment_depth += 1
                comment_buffer.append(two)
                i += 2
                continue
            if two == "*)":
                comment_depth -= 1
                comment_buffer.append(two)
                if comment_depth == 0:
                    comment_text = "".join(comment_buffer)
                    if comment_text.lstrip().startswith("(**"):
                        doc_buffer = [comment_text]
                    comment_buffer = []
                    i += 2
                    continue
                i += 2
                continue
            comment_buffer.append(char)
            i += 1
            continue

        buffer.append(char)

        if not in_string and char == ".":
            statement_text = "".join(buffer).strip()
            if statement_text:
                yield Statement(
                    text=statement_text,
                    leading_doc=clean_comment("".join(doc_buffer)) if doc_buffer else "",
                    line=statement_start_line,
                )
            buffer = []
            doc_buffer = []
            statement_start_line = line

        i += 1


def iter_declarations(file_path: Path, root: SourceRoot) -> Iterator[Declaration]:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    module = module_name(file_path, root.path)
    relative_file = file_path.relative_to(root.path).as_posix()

    for statement in iter_statements(text):
        matchable = strip_comments_for_match(statement.text)
        match = DECLARATION_RE.match(matchable)
        if not match:
            continue

        name = match.group("name")
        kind = match.group("kind")
        rest = match.group("rest").removesuffix(".")
        yield Declaration(
            name=name,
            kind=kind,
            type_signature=extract_type(rest),
            statement=compact_ws(matchable),
            docstring=statement.leading_doc,
            module_path=module,
            library=root.library,
            file_path=relative_file,
            source_path=str(file_path),
            line_number=statement.line,
            github_url=make_github_url(root.library, relative_file, statement.line),
        )


def iter_v_files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*.v") if path.is_file())


def extract(sources: list[SourceRoot], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as out:
        for source in sources:
            if not source.path.exists():
                raise FileNotFoundError(f"Source root does not exist: {source.path}")
            for file_path in iter_v_files(source.path):
                for declaration in iter_declarations(file_path, source):
                    out.write(json.dumps(asdict(declaration), ensure_ascii=False) + "\n")
                    count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Library source as PATH=library, e.g. ~/code/math-comp/mathcomp=mathcomp",
    )
    parser.add_argument(
        "--out",
        default="data/declarations.jsonl",
        help="Output JSONL path. Defaults to data/declarations.jsonl",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sources = [parse_source(value) for value in args.source]
    count = extract(sources=sources, out_path=Path(args.out).resolve())
    print(f"Wrote {count} declarations to {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
