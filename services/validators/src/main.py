"""M9 HTTP API: POST /score-all runs the four scorers in parallel."""
from __future__ import annotations

import httpx
from pydantic import BaseModel

from common.app import create_app
from common.config import SERVICE_URLS

from .agents import run_all

app, metrics = create_app("validators")


class ScoreAllIn(BaseModel):
    run_id: str
    idea: str
    profile: dict
    niche_slope: float = 0.0


@app.post("/score-all")
def score_all(b: ScoreAllIn):
    def search(q: str, filters: dict) -> list[dict]:
        r = httpx.post(f"{SERVICE_URLS['kb']}/search", timeout=30,
                       json={"query": q, "k": 8, "run_id": b.run_id, **filters})
        r.raise_for_status()
        return r.json()["results"]

    def score(dim, idea, evidence, profile, features):
        r = httpx.post(f"{SERVICE_URLS['scorer']}/score", timeout=120, json={
            "run_id": b.run_id, "dimension": dim, "idea": idea, "evidence": evidence,
            "profile": profile, "features": features})
        r.raise_for_status()
        return r.json()

    res = run_all(b.idea, b.profile, search, score, b.niche_slope)
    metrics.inc("validations_total")
    return res
