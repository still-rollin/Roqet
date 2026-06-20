"""The roqet -> rocqet rename must not break deployments using the legacy
ROQET_* environment prefix. rocqet/__init__.py maps it onto ROCQET_* at import
time; verify in a fresh interpreter (the shim runs once, at import)."""

import subprocess
import sys


def test_legacy_env_prefix_is_honored():
    code = (
        "import os, rocqet;"
        "print(os.environ.get('ROCQET_EMBEDDER'))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        env={"PATH": "/usr/bin:/bin", "ROQET_EMBEDDER": "fastembed"},
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "fastembed"


def test_new_prefix_takes_precedence():
    code = "import os, rocqet; print(os.environ.get('ROCQET_EMBEDDER'))"
    out = subprocess.run(
        [sys.executable, "-c", code],
        env={"PATH": "/usr/bin:/bin", "ROQET_EMBEDDER": "legacy", "ROCQET_EMBEDDER": "new"},
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "new"
