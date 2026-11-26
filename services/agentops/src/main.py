"""M13 HTTP API.
POST /trace, GET /runs/{id}/trace      tracing (JSONL on a volume + memory index)
POST/GET /records/{id}                 recorded tool results for replay
POST /verdicts                         verdict log (for distribution + drift)
GET  /summary, /dashboard, /metrics    dashboard numbers / HTML page / Prometheus
POST /drift                            drift report after each ingestion
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from common.app import create_app
from common.config import SERVICE_URLS
from common.schemas import TraceRecord

from .core import drift_report, summarise

DATA = Path(os.environ.get("TRACE_DIR", "/data/traces"))
DATA.mkdir(parents=True, exist_ok=True)
app, metrics = create_app("agentops")
TRACES: dict[str, list[dict]] = defaultdict(list)
VERDICTS: list[dict] = []


def _load():
    for f in sorted(DATA.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            t = json.loads(line)
            TRACES[t["run_id"]].append(t)
    vf = DATA / "verdicts.json"
    if vf.exists():
        VERDICTS.extend(json.loads(vf.read_text()))


_load()


@app.post("/trace")
def trace(t: TraceRecord):
    d = t.model_dump()
    TRACES[t.run_id].append(d)
    with (DATA / f"{date.today().isoformat()}.jsonl").open("a") as f:
        f.write(json.dumps(d) + "\n")
    metrics.inc("trace_records_total", agent=t.agent)
    metrics.inc("agent_cost_usd_total", value=t.cost_usd, agent=t.agent)
    metrics.observe("agent_step", t.latency_ms / 1000, agent=t.agent)
    if t.cache_hit:
        metrics.inc("cache_hits_total")
    return {"ok": True}


@app.get("/runs/{run_id}/trace")
def get_trace(run_id: str):
    recs = TRACES.get(run_id) or [t for k, v in TRACES.items() if k.startswith(run_id + "_") for t in v]
    if not recs:
        raise HTTPException(404, "no trace")
    return sorted(recs, key=lambda t: t["ts"])


@app.post("/records/{run_id}")
def save_record(run_id: str, body: dict):
    (DATA / f"record_{run_id}.json").write_text(json.dumps(body))
    return {"ok": True}


@app.get("/records/{run_id}")
def get_record(run_id: str):
    p = DATA / f"record_{run_id}.json"
    if not p.exists():
        raise HTTPException(404)
    return json.loads(p.read_text())


@app.post("/verdicts")
def log_verdict(v: dict):
    VERDICTS.append({k: v.get(k) for k in ("run_id", "idea_id", "version", "verdict", "score", "stability")}
                    | {"ts": datetime.utcnow().isoformat()})
    (DATA / "verdicts.json").write_text(json.dumps(VERDICTS))
    metrics.inc("verdicts_total", verdict=str(v.get("verdict")))
    return {"ok": True}


@app.get("/summary")
def summary():
    return summarise([t for v in TRACES.values() for t in v], VERDICTS)


@app.post("/drift")
def drift(window: int = 50):
    stats = httpx.get(f"{SERVICE_URLS['kb']}/stats", timeout=30).json()
    today = date.today()
    fresh = {s: (today - date.fromisoformat(d)).days if d and d != "None" else None
             for s, d in stats.get("newest_fetch", {}).items()}
    vs = [v["verdict"] for v in VERDICTS]
    rep = drift_report(stats, fresh, vs[-2 * window:-window], vs[-window:])
    rep["generated_at"] = datetime.utcnow().isoformat()
    out = Path(os.environ.get("EVAL_RESULTS", "/data/eval-results"))
    out.mkdir(parents=True, exist_ok=True)
    (out / f"drift-{today.isoformat()}.json").write_text(json.dumps(rep, indent=2))
    return rep


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (Path(__file__).parent / "dashboard.html").read_text()
