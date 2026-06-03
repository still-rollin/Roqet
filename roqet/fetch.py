"""Clone or update major Rocq/Coq libraries for extraction."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Library:
    name: str
    repo: str
    subdir: str
    branch: str = "master"
    sparse: bool = False


LIBRARIES = {
    "stdlib": Library("stdlib", "https://github.com/rocq-prover/rocq.git", "theories", "master", True),
    "mathcomp": Library("mathcomp", "https://github.com/math-comp/math-comp.git", "."),
    "unimath": Library("unimath", "https://github.com/UniMath/UniMath.git", "UniMath"),
    "hott": Library("hott", "https://github.com/HoTT/Coq-HoTT.git", "theories"),
    "iris": Library("iris", "https://gitlab.mpi-sws.org/iris/iris.git", ".", "master"),
}


def run(args: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=cwd, check=True)


def clone_or_update(library: Library, repos_dir: Path) -> Path:
    target = repos_dir / library.name
    if target.exists():
        run(["git", "fetch", "--depth", "1", "origin", library.branch], cwd=target)
        run(["git", "checkout", library.branch], cwd=target)
        run(["git", "pull", "--ff-only"], cwd=target)
        return target / library.subdir

    if library.sparse:
        run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                "--branch",
                library.branch,
                library.repo,
                str(target),
            ]
        )
        run(["git", "sparse-checkout", "set", library.subdir], cwd=target)
    else:
        run(["git", "clone", "--depth", "1", "--branch", library.branch, library.repo, str(target)])
    return target / library.subdir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-dir", type=Path, default=Path("repos"))
    parser.add_argument("--lib", action="append", choices=sorted(LIBRARIES), help="Library to fetch. Repeatable.")
    args = parser.parse_args(argv)

    args.repos_dir.mkdir(parents=True, exist_ok=True)
    names = args.lib or list(LIBRARIES)
    for name in names:
        source = clone_or_update(LIBRARIES[name], args.repos_dir)
        print(f"{name}: {source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
