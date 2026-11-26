"""M7 HTTP API. POST /analyse recomputes niches from the KB (also run as a
step of the ingestion CronJob). GET /niches, GET /gaps."""
from __future__ import annotations

import httpx

from common.app import create_app
from common.config import SERVICE_URLS

from .core import analyse

app, metrics = create_app("analyst")
STATE: dict = {"niches": [], "assignments": {}}


def _embed_and_tok():
    from common.embedding import get_embedder
    from common.text import tokenize
    return get_embedder(), tokenize


@app.post("/analyse")
def run_analysis(k: int = 12):
    cards = httpx.get(f"{SERVICE_URLS['kb']}/cards", timeout=120).json()
    embed, tok = _embed_and_tok()
    STATE.update(analyse(cards, embed, tok, k=k))
    metrics.inc("analyses_total")
    return {"niches": len(STATE["niches"]), "cards": len(cards)}


@app.get("/niches")
def niches(interest: str = ""):
    ns = STATE["niches"]
    if interest:
        ns = [n for n in ns if any(interest.lower() in kw for kw in n["keywords"])] or ns
    return [{k: v for k, v in n.items() if k != "card_ids"} for n in ns]


@app.get("/gaps")
def gaps(niche_id: str = ""):
    return [dict(g, niche_id=n["id"], niche=n["name"]) for n in STATE["niches"]
            if not niche_id or n["id"] == niche_id for g in n["gaps"]]
