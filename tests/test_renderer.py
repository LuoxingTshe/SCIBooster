import pytest
from fastapi.testclient import TestClient

from renderer.server import create_app
from scibooster.store import CorpusStore


@pytest.fixture
def client(small_corpus, tmp_path):
    path = CorpusStore(small_corpus).save(tmp_path / "corpus.json")
    return TestClient(create_app(path))


def test_index_and_corpus(client):
    html = client.get("/").text
    assert "cytoscape" in html and "RAG" not in html and 'data-tab="ask"' not in html
    assert client.post("/api/ask", json={"question": "x"}).status_code in (404, 405)
    assert client.get("/static/app.js").status_code == 200
    data = client.get("/api/corpus").json()
    assert len(data["papers"]) == 7 and data["edges"]
    assert "referenced_works" not in data["papers"][0]


def test_traverse_api(client):
    r = client.get("/api/traverse", params={"start": "W5", "mode": "bfs", "direction": "cited_by", "depth": 5})
    assert [v["id"] for v in r.json()["visits"]] == ["W5", "W6", "W7", "W8"]
    r = client.get("/api/traverse", params=[("start", "W8"), ("start", "W1"), ("mode", "dfs")])
    assert r.status_code == 200 and r.json()["visits"][0]["id"] == "W8"
    assert client.get("/api/traverse", params={"start": "NOPE"}).status_code == 404
