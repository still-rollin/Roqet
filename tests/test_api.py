"""Smoke tests for the API that need no Qdrant / embedder backend."""

from fastapi.testclient import TestClient

from rocqet import api


def test_health_ok():
    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "collection" in body


def test_build_filter_none_when_empty():
    assert api.build_filter(None, None) is None
    assert api.build_filter("", "  ") is None


def test_build_filter_single_field():
    f = api.build_filter("stdlib", None)
    assert f is not None
    assert len(f.must) == 1
    cond = f.must[0]
    assert cond.key == "library"
    assert cond.match.any == ["stdlib"]


def test_build_filter_comma_list_and_multiple_fields():
    f = api.build_filter("stdlib,mathcomp", "Lemma", chapter="Ch02")
    keys = {c.key: c.match.any for c in f.must}
    assert keys["library"] == ["stdlib", "mathcomp"]
    assert keys["kind"] == ["Lemma"]
    assert keys["chapter"] == ["Ch02"]
