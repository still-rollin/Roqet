"""Pure-function tests for the offline NL-description tooling (no network)."""

import json

from rocqet import describe


def test_decl_line_uses_signature_then_statement():
    d = {"kind": "Lemma", "name": "addnC", "type_signature": "forall n m, n + m = m + n"}
    line = describe.decl_line(3, d)
    assert line.startswith("[3] Lemma addnC ::")
    assert "n + m = m + n" in line


def test_load_cache_roundtrip(tmp_path):
    path = tmp_path / "cache.jsonl"
    path.write_text(
        json.dumps({"id": 1, "name": "a", "nl_description": "first"}) + "\n"
        + json.dumps({"id": 2, "name": "b", "nl_description": "second"}) + "\n",
        encoding="utf-8",
    )
    cache = describe.load_cache(path)
    assert cache == {1: "first", 2: "second"}


def test_load_cache_missing_file(tmp_path):
    assert describe.load_cache(tmp_path / "nope.jsonl") == {}
