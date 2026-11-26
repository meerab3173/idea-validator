"""Scouts: CLI for the CronJob (`python -m src.main --source hn`) and an
HTTP API for on-demand scouting during Validate (POST /scout)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel

from common.config import SERVICE_URLS
from common.trace import span

from .sources import SOURCES, run_source

RAW_DIR = Path(os.environ.get("RAW_DIR", "/data/raw"))


def make_fetch(run_id: str):
    def fetch(url: str) -> dict:
        r = httpx.post(f"{SERVICE_URLS['tools']}/fetch", json={"url": url, "run_id": run_id}, timeout=60)
        r.raise_for_status()
        return r.json()
    return fetch


def save_and_ingest(result: dict, ingest: bool = True) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{result['source']}.jsonl"
    with out.open("a") as f:
        for c in result["cards"]:
            f.write(json.dumps(c) + "\n")
    if ingest and result["cards"]:
        httpx.post(f"{SERVICE_URLS['kb']}/ingest", json={"source": result["source"],
                                                         "cards": result["cards"]}, timeout=600)
    return out


def cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=list(SOURCES), required=True)
    ap.add_argument("--query", default="")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--no-ingest", action="store_true")
    a = ap.parse_args()
    kw = {"pages": a.pages}
    if a.query:
        kw["query"] = a.query
    run_id = f"scout-{a.source}"
    with span(run_id, f"scout_{a.source}", "tool_call", tool="scout", input=json.dumps(kw)) as s:
        res = run_source(a.source, make_fetch(run_id), **kw)
        save_and_ingest(res, ingest=not a.no_ingest)
        s["output"] = f"{len(res['cards'])} cards, {len(res['errors'])} errors"
    print(json.dumps({"source": a.source, "cards": len(res["cards"]), "errors": res["errors"][:5]}))
    # Exit 0 even with some page errors; fail only if the whole source failed.
    return 1 if not res["cards"] and res["errors"] else 0


# ---------------------------------------------------------------- on-demand API
from common.app import create_app  # noqa: E402

app, metrics = create_app("scouts")


class ScoutIn(BaseModel):
    run_id: str
    query: str
    sources: list[str] = ["hn", "github"]
    pages: int = 1


@app.post("/scout")
def scout(body: ScoutIn):
    total, errors = 0, []
    for src in body.sources:
        kw = {"pages": body.pages}
        if src in ("hn", "github"):
            kw["query"] = body.query
        res = run_source(src, make_fetch(body.run_id), **kw)
        save_and_ingest(res)
        total += len(res["cards"])
        errors += res["errors"]
        metrics.inc("scout_cards_total", value=len(res["cards"]), source=src)
    return {"cards_added": total, "errors": errors}


if __name__ == "__main__":
    sys.exit(cli())
