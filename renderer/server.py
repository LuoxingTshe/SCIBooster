"""Renderer backend: serves the frontend, the corpus, and BFS/DFS traversal."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scibooster.graph import build_graph, traverse, visits_to_dicts
from scibooster.store import CorpusStore

STATIC = Path(__file__).parent / "static"


def create_app(corpus_path: Path) -> FastAPI:
    corpus = CorpusStore.load(corpus_path).finalize()
    g = build_graph(corpus)
    app = FastAPI(title="SCIBooster Renderer")

    @app.get("/api/corpus")
    def get_corpus():
        data = corpus.model_dump(exclude={"papers": {"__all__": {"referenced_works"}}})
        data["meta"]["source_file"] = str(corpus_path)
        return data

    @app.get("/api/traverse")
    def get_traverse(
        start: list[str] = Query(...),
        mode: Literal["bfs", "dfs"] = "bfs",
        direction: Literal["refs", "cited_by", "both"] = "both",
        depth: int = Query(3, ge=0, le=12),
        limit: int = Query(200, ge=1, le=2000),
    ):
        unknown = [s for s in start if s not in g]
        if unknown:
            raise HTTPException(404, f"unknown paper id(s): {', '.join(unknown)}")
        visits = traverse(g, start, mode=mode, direction=direction, max_depth=depth, limit=limit)
        return {"mode": mode, "direction": direction, "visits": visits_to_dicts(visits)}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
