"""M6 HTTP API: POST /search, POST /ingest, POST /evidence, GET /stats, GET /cards."""
from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from common.app import create_app
from common.trace import span

from .core import Filters
from common.embedding import get_embedder, get_reranker

embed, rerank = get_embedder(), get_reranker()
repo = None


async def ready() -> bool:
    try:
        repo.conn.execute("SELECT 1")
        return True
    except Exception:
        return False


app, metrics = create_app("kb", ready)


@app.on_event("startup")
def _startup():
    global repo
    from .pg import KBRepo, connect, migrate
    conn = connect()
    migrate(conn)
    repo = KBRepo(conn, embed, rerank)


class SearchIn(BaseModel):
    query: str
    k: int = 8
    mode: str = "hybrid"
    run_id: str = "adhoc"
    source: Optional[list[str]] = None
    niche: Optional[list[str]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@app.post("/search")
def search(b: SearchIn):
    with span(b.run_id, "kb", "tool_call", tool="search_kb", input=b.query) as s:
        res = repo.search(b.query, b.k, Filters(b.source, b.niche, b.date_from, b.date_to), b.mode)
        s["output"] = json.dumps([r["evidence_id"] for r in res])
    metrics.inc("kb_search_total", mode=b.mode)
    return {"results": res}


class IngestIn(BaseModel):
    source: str
    cards: list[dict]


@app.post("/ingest")
def ingest(b: IngestIn):
    r = repo.ingest(b.source, b.cards)
    metrics.inc("kb_cards_added_total", value=r["added"], source=b.source)
    return r


class EvidenceIn(BaseModel):
    ids: list[str]


@app.post("/evidence")
def evidence(b: EvidenceIn):
    """Used by the critic (M12): returns the text for each evidence id, or null."""
    return repo.evidence_exists(b.ids)


@app.get("/stats")
def stats():
    return repo.stats()


@app.get("/cards")
def cards():
    return repo.all_cards()
