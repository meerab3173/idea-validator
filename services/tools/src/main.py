"""M5 HTTP API. POST /fetch {url, run_id, as_json}. Only this pod may reach
the internet (k8s/networkpolicy.yaml)."""
from __future__ import annotations

import json
import os
import time

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from common.app import create_app
from common.trace import span

from .core import (DEFAULT_ALLOW, USER_AGENT, Blocked, RateLimiter, Robots, TokenBucket, TTLCache, check_allowed,
                   sanitise)

app, metrics = create_app("tools")

ALLOW = dict(DEFAULT_ALLOW)
if os.environ.get("ALLOW_LIST"):  # "host=rps,host=rps" from the ConfigMap
    ALLOW = {h: float(r) for h, r in (x.split("=") for x in os.environ["ALLOW_LIST"].split(","))}

limiter = RateLimiter(ALLOW)
cache = TTLCache(int(os.environ.get("FETCH_CACHE_TTL", "3600")))
client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=False)
MAX_PAGES_PER_RUN = int(os.environ.get("MAX_PAGES_PER_RUN", "200"))
pages_by_run: dict[str, int] = {}


def _robots_text(url: str):
    try:
        r = client.get(url)
        return r.text if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


robots = Robots(_robots_text)


class FetchIn(BaseModel):
    url: str
    run_id: str = "scheduled"
    as_json: bool = True
    headers: dict[str, str] = {}


@app.post("/fetch")
def fetch(body: FetchIn):
    with span(body.run_id, "tool_layer", "tool_call", tool="fetch", input=body.url) as s:
        try:
            host = check_allowed(body.url, ALLOW)
        except Blocked as e:
            metrics.inc("fetch_blocked_total", reason="allowlist")
            raise HTTPException(403, str(e))

        n = pages_by_run.get(body.run_id, 0)
        if n >= MAX_PAGES_PER_RUN:
            metrics.inc("fetch_blocked_total", reason="budget")
            raise HTTPException(429, "page budget for this run exhausted")

        hit = cache.get(body.url)
        if hit is not None:
            s["cache_hit"] = True
            metrics.inc("fetch_cache_hits_total")
            return hit

        if not robots.allowed(body.url):
            metrics.inc("fetch_blocked_total", reason="robots")
            raise HTTPException(403, "disallowed by robots.txt")

        limiter.wait(host)
        pages_by_run[body.run_id] = n + 1
        # Secrets (GitHub token, Reddit token) are added here, never by callers.
        headers = dict(body.headers)
        if host == "api.github.com" and os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

        for attempt in range(3):  # back-off on errors
            try:
                r = client.get(body.url, headers=headers)
                if r.status_code in (429, 500, 502, 503):
                    time.sleep(2 ** attempt)
                    continue
                break
            except httpx.HTTPError as e:
                s["retries"] = attempt + 1
                if attempt == 2:
                    raise HTTPException(502, f"fetch failed: {e}")
                time.sleep(2 ** attempt)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, "upstream error")

        if body.as_json:
            data = r.json()
            flagged = _sanitise_json(data)
            out = {"url": body.url, "json": data, "flagged": flagged}
        else:
            sz = sanitise(r.text)
            flagged = sz.removed
            out = {"url": body.url, "text": sz.text, "flagged": flagged}
        if flagged:
            metrics.inc("injections_blocked_total", value=len(flagged))
        cache.set(body.url, out)
        metrics.inc("fetch_total", host=host)
        s["output"] = f"{r.status_code} {len(r.content)}B flagged={len(flagged)}"
        return out


def _sanitise_json(obj) -> list[str]:
    """Sanitise every string inside a JSON response in place."""
    removed: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                sz = sanitise(v)
                obj[k] = sz.text
                removed += sz.removed
            else:
                removed += _sanitise_json(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                sz = sanitise(v)
                obj[i] = sz.text
                removed += sz.removed
            else:
                removed += _sanitise_json(v)
    return removed


# ---------------------------------------------------------------- hosted-LLM egress
# Agents never call the internet themselves: hosted-model calls also leave the
# cluster through M5. The API key lives ONLY in this pod's Secret.
from fastapi import Request  # noqa: E402

LLM_UPSTREAM = os.environ.get("LLM_UPSTREAM", "https://api.groq.com/openai/v1")
LLM_KEY = os.environ.get("LLM_UPSTREAM_KEY", "")
llm_client = httpx.Client(timeout=90)


@app.post("/llm/v1/chat/completions")
async def llm_proxy(request: Request):
    host = check_allowed(LLM_UPSTREAM + "/", {**ALLOW, httpx.URL(LLM_UPSTREAM).host: 2.0})
    body = await request.json()
    limiter.buckets.setdefault(host, TokenBucket(rate=2.0))
    limiter.wait(host)
    r = llm_client.post(f"{LLM_UPSTREAM}/chat/completions", json=body,
                        headers={"Authorization": f"Bearer {LLM_KEY}"})
    metrics.inc("llm_proxy_calls_total", status=str(r.status_code))
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return r.json()
