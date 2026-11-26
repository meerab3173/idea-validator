"""M12 HTTP API: POST /check, /rail, /scan, /approval."""
from __future__ import annotations

import httpx
from pydantic import BaseModel

from common.app import create_app
from common.config import SERVICE_URLS
from common.schemas import Claim
from common.trace import span

from .core import check_claims, input_rail, needs_approval, scan_injection

app, metrics = create_app("critic")


class CheckIn(BaseModel):
    run_id: str = "adhoc"
    claims: list[Claim]


@app.post("/check")
def check(b: CheckIn):
    ids = sorted({i for c in b.claims for i in c.evidence_ids})
    texts = httpx.post(f"{SERVICE_URLS['kb']}/evidence", json={"ids": ids}, timeout=30).json() if ids else {}
    with span(b.run_id, "critic", "decision", tool="check_claims", input=str([c.claim_id for c in b.claims])) as s:
        res = check_claims(b.claims, texts)
        s["output"] = str([(r.claim_id, r.supported) for r in res])
    metrics.inc("claims_checked_total", value=len(res))
    metrics.inc("claims_rejected_total", value=sum(not r.supported for r in res))
    return {"results": [r.model_dump() for r in res]}


class TextIn(BaseModel):
    text: str


@app.post("/rail")
def rail(b: TextIn):
    ok, msg = input_rail(b.text)
    if not ok:
        metrics.inc("input_rail_blocked_total")
    return {"ok": ok, "message": msg}


@app.post("/scan")
def scan(b: TextIn):
    hits = scan_injection(b.text)
    if hits:
        metrics.inc("injections_blocked_total", value=len(hits))
    return {"injection": bool(hits), "matches": hits}


class ApprovalIn(BaseModel):
    estimated_cost: float
    spent: float
    budget: float


@app.post("/approval")
def approval(b: ApprovalIn):
    return {"needs_approval": needs_approval(b.estimated_cost, b.spent, b.budget)}
