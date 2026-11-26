"""M3 HTTP API (internal; the browser only talks to M1).

POST /validate, /discover                 start a run (background thread)
GET  /runs/{id}, /runs/{id}/events        status/result, SSE progress stream
POST /runs/{id}/answer, /runs/{id}/approve
POST /ideas/challenge, /ideas/whatif/propose, /ideas/whatif/apply
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from typing import Optional

import httpx
import yaml
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from common.app import create_app
from common.config import SERVICE_URLS, env
from common.schemas import TraceRecord
from common.trace import emit

from .machine import RecordingClients, S, ValidateMachine, discover

U = SERVICE_URLS
app, metrics = create_app("orchestrator")
CFG = yaml.safe_load(open(env("BUDGETS_CONFIG", "/config/budgets.yaml")))
RUBRIC_SET = yaml.safe_load(open(env("RUBRIC_REGISTRY", "/rubrics/REGISTRY.yaml")))["set"]
http = httpx.Client(timeout=180)

RUNS: dict[str, dict] = {}          # run_id -> {"kind", "state", "machine_run", "result", "events"}
CACHE: dict = {}                    # score cache (Redis-backed cache lives in M2 for verdicts)


def post(svc: str, path: str, body: dict):
    r = http.post(f"{U[svc]}{path}", json=body)
    r.raise_for_status()
    return r.json()


class HttpClients:
    def rail(self, text): return post("critic", "/rail", {"text": text})

    def kb_stats_for(self, run_id, idea):
        res = post("kb", "/search", {"query": idea, "k": 20, "run_id": run_id})["results"]
        return {"n_sources": len({e["card_id"] for e in res}), "n_platforms": len({e["source"] for e in res})}

    def scout(self, run_id, q):
        return http.post(f"{env('SCOUTS_URL', 'http://scouts:8000')}/scout",
                         json={"run_id": run_id, "query": q, "sources": ["hn", "github"]}).json()

    def score_all(self, run_id, idea, profile):
        return post("validators", "/score-all", {"run_id": run_id, "idea": idea, "profile": profile})

    def verdict(self, p): return post("verdict", "/verdict", p)
    def challenge_verdict(self, p): return post("verdict", "/challenge", p)
    def skeptic(self, run_id, idea, ev): return post("ideation", "/skeptic", {"run_id": run_id, "idea": idea, "evidence": ev})["objections"]
    def critic(self, run_id, claims): return post("critic", "/check", {"run_id": run_id, "claims": claims})["results"]
    def niches(self, interest): return http.get(f"{U['analyst']}/niches", params={"interest": interest}).json()
    def generate(self, run_id, profile, niche, n): return post("ideation", "/generate", {"run_id": run_id, "profile": profile, "niche": niche, "n_ideas": n})

    def save(self, kind, payload):
        try:
            http.post(f"{env('PROFILE_URL', 'http://profile:8000')}/internal/save/{kind}", json=payload)
            if kind == "verdict":
                http.post(f"{U['agentops']}/verdicts", json=payload["card"])
        except httpx.HTTPError:
            pass


clients = HttpClients()


def on_event(e: dict) -> None:
    rid = e["run_id"]
    run = RUNS.get(rid) or RUNS.get(rid.rsplit("_", 1)[0])  # Discover sub-runs: run_x_0 -> run_x
    if run is not None:
        run["events"].append(e)
    emit(TraceRecord(run_id=e["run_id"], step_id=len(run["events"]) if run else 0, agent=e.get("agent", "orchestrator"),
                     kind="decision", output=json.dumps(e)[:1000]), post=True)


vm = ValidateMachine(clients, CFG, CACHE, RUBRIC_SET, on_event)


def _sync(run_id: str) -> None:
    r = RUNS[run_id]
    m = r.get("machine_run")
    if m is not None:
        r["state"] = m.state.value
        r["result"] = m.verdict if m.state == S.DONE else None
        r["questions"] = m.questions if m.state == S.CLARIFY else []
        r["error"] = m.error
        r["spend_usd"] = round(m.budget.cost, 5)


def _bg(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


# ---------------------------------------------------------------- endpoints
class ValidateIn(BaseModel):
    idea: str
    profile: dict
    idea_id: str = ""
    version: int = 1


def _save_tape(run_id: str) -> None:
    """Store the recorded tool/model results so `scripts/replay.sh <run_id>` works."""
    rec = RUNS[run_id].get("recorder")
    if rec is None:
        return
    try:
        http.post(f"{U['agentops']}/records/{run_id}", json={"tape": rec.tape,
                  "idea": RUNS[run_id]["machine_run"].idea, "profile": RUNS[run_id]["machine_run"].profile})
    except httpx.HTTPError:
        pass


@app.post("/validate")
def start_validate(b: ValidateIn):
    rec = RecordingClients(clients)
    run_vm = ValidateMachine(rec, CFG, CACHE, RUBRIC_SET, on_event)
    m = run_vm.new(b.idea, b.profile, b.idea_id, b.version)
    RUNS[m.run_id] = {"kind": "validate", "state": m.state.value, "machine_run": m, "events": [],
                      "idea_id": m.idea_id, "vm": run_vm, "recorder": rec}

    def go():
        run_vm.run(m); _sync(m.run_id); _save_tape(m.run_id)
    _bg(go)
    metrics.inc("runs_started_total", kind="validate")
    return {"run_id": m.run_id, "idea_id": m.idea_id}


class DiscoverIn(BaseModel):
    profile: dict
    niche: str = ""
    n_ideas: int = 5


@app.post("/discover")
def start_discover(b: DiscoverIn):
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    RUNS[run_id] = {"kind": "discover", "state": "RUNNING", "events": [], "result": None}

    def go():
        try:
            res = discover(clients, vm, b.profile, b.niche, run_id, b.n_ideas, on_event)
            RUNS[run_id].update(state="DONE", result=res)
            clients.save("discover", {"run_id": run_id, "profile": b.profile, "result": res})
        except Exception as e:  # noqa: BLE001
            RUNS[run_id].update(state="FAILED", error=repr(e))
    _bg(go)
    metrics.inc("runs_started_total", kind="discover")
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404)
    _sync(run_id)
    r = RUNS[run_id]
    return {k: v for k, v in r.items() if k not in ("machine_run", "vm", "recorder")}


@app.get("/runs/{run_id}/events")
async def events(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404)

    async def stream():
        i = 0
        while True:
            evs = RUNS[run_id]["events"]
            while i < len(evs):
                yield f"data: {json.dumps(evs[i], default=str)}\n\n"
                i += 1
            _sync(run_id)
            st = RUNS[run_id]["state"]
            if st in ("DONE", "FAILED", "CLARIFY", "AWAIT_APPROVAL"):
                yield f"event: end\ndata: {json.dumps({'state': st})}\n\n"
                return
            await asyncio.sleep(0.3)
    return StreamingResponse(stream(), media_type="text/event-stream")


class AnswerIn(BaseModel):
    answers: dict


@app.post("/runs/{run_id}/answer")
def answer(run_id: str, b: AnswerIn):
    m, rvm = RUNS[run_id]["machine_run"], RUNS[run_id]["vm"]
    _bg(lambda: (rvm.answer(m, b.answers), _sync(run_id), _save_tape(run_id)))
    return {"ok": True}


class ApproveIn(BaseModel):
    approve: bool


@app.post("/runs/{run_id}/approve")
def approve(run_id: str, b: ApproveIn):
    m, rvm = RUNS[run_id]["machine_run"], RUNS[run_id]["vm"]
    _bg(lambda: (rvm.approve(m, b.approve), _sync(run_id), _save_tape(run_id)))
    return {"ok": True}


class UserChallengeIn(BaseModel):
    run_id: str
    card: dict
    dimension: str
    profile: dict


@app.post("/ideas/challenge")
def user_challenge(b: UserChallengeIn):
    """U8: re-check the scorer's claim for one dimension against its evidence.
    Supported -> defended. Not supported -> removed (score penalty) and M11 re-runs."""
    s = next(x for x in b.card["scores"] if x["dimension"] == b.dimension)
    res = clients.critic(b.run_id, [{"claim_id": b.dimension, "text": s.get("reason", ""),
                                     "evidence_ids": s.get("evidence_ids", [])}])[0]
    if res["supported"]:
        return {"outcome": "defended", "reason": res["reason"], "card": b.card}
    payload = {"idea_id": b.card["idea_id"], "version": b.card["version"], "run_id": b.run_id,
               "scores": b.card["scores"], "profile": b.profile, "gates": b.card.get("gate_inputs") or {},
               "rubric_version": RUBRIC_SET, "accepted": {b.dimension: 2}}
    new = clients.challenge_verdict(payload)
    return {"outcome": "removed", "reason": res["reason"], "card": {**b.card, **new}}


class WhatIfProposeIn(BaseModel):
    run_id: str
    idea: str
    card: dict


@app.post("/ideas/whatif/propose")
def whatif_propose(b: WhatIfProposeIn):
    """U7: turn the engine's smallest changes into concrete idea changes."""
    return post("ideation", "/concretize", {"run_id": b.run_id, "idea": b.idea,
                                            "options": b.card.get("what_would_make_go", [])[:3],
                                            "evidence": b.card.get("evidence", [])[:10]})


class WhatIfApplyIn(BaseModel):
    idea_id: str
    version: int
    new_idea_text: str
    profile: dict


@app.post("/ideas/whatif/apply")
def whatif_apply(b: WhatIfApplyIn):
    """Creates version N+1: re-runs the scorers and the engine on the changed idea."""
    return start_validate(ValidateIn(idea=b.new_idea_text, profile=b.profile,
                                     idea_id=b.idea_id, version=b.version + 1))
