"""M1 API Gateway: the only public entrance. Login, rate limits, input
validation, then forwards to internal services. The browser never calls
models, scouts or internal services directly."""
from __future__ import annotations

import os

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from common.app import create_app
from common.config import SERVICE_URLS, env

from .security import (MemoryCounter, RedisCounter, allowed, hash_password, make_token, read_token,
                       verify_password)

U = SERVICE_URLS
PROFILE = env("PROFILE_URL", "http://profile:8000")
RUBRIC_SET = env("RUBRIC_SET", "r1")
app, metrics = create_app("gateway")
app.add_middleware(CORSMiddleware, allow_origins=env("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
http = httpx.Client(timeout=60)
counter = RedisCounter(env("REDIS_URL")) if env("REDIS_URL") else MemoryCounter()


def fwd(method: str, url: str, **kw):
    try:
        r = http.request(method, url, **kw)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"upstream unavailable: {e.__class__.__name__}")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.json().get("detail", "error") if r.headers.get(
            "content-type", "").startswith("application/json") else "error")
    return r.json()


def limit(bucket: str):
    def dep(request: Request):
        who = request.headers.get("authorization", "") or (request.client.host if request.client else "?")
        if not allowed(counter, who[-24:], bucket):
            metrics.inc("rate_limited_total", bucket=bucket)
            raise HTTPException(429, "Too many requests, slow down")
    return dep


def user(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    uid = read_token(auth.removeprefix("Bearer ").strip()) if auth.startswith("Bearer ") else None
    if not uid:
        raise HTTPException(401, "login required")
    return uid


# ---------------------------------------------------------------- auth
class Creds(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


@app.post("/auth/register", dependencies=[Depends(limit("auth"))])
def register(b: Creds):
    u = fwd("POST", f"{PROFILE}/users", json={"email": b.email, "password_hash": hash_password(b.password)})
    return {"token": make_token(u["id"]), "user_id": u["id"]}


@app.post("/auth/login", dependencies=[Depends(limit("auth"))])
def login(b: Creds):
    try:
        u = fwd("GET", f"{PROFILE}/users/by-email/{b.email}")
    except HTTPException:
        u = None
    if not u or not verify_password(b.password, u["hash"]):
        raise HTTPException(401, "wrong email or password")
    return {"token": make_token(u["id"]), "user_id": u["id"]}


# ---------------------------------------------------------------- profile
class ProfileIn(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=30)
    hours_per_week: float = Field(ge=1, le=80)
    weeks_available: int = Field(ge=1, le=104)
    team_size: int = Field(ge=1, le=10)
    compute: str = Field(pattern="^(laptop|free_gpu|paid)$")
    goal: str = Field(pattern="^(startup|portfolio|course_project)$")
    interests: list[str] = Field(default_factory=list, max_length=30)


@app.get("/profile", dependencies=[Depends(limit("default"))])
def get_profile(uid: str = Depends(user)):
    return fwd("GET", f"{PROFILE}/profiles/{uid}")


@app.put("/profile", dependencies=[Depends(limit("default"))])
def put_profile(b: ProfileIn, uid: str = Depends(user)):
    return fwd("PUT", f"{PROFILE}/profiles/{uid}", json=b.model_dump())


# ---------------------------------------------------------------- runs
class DiscoverIn(BaseModel):
    niche: str = Field(default="", max_length=100)
    n_ideas: int = Field(default=5, ge=1, le=8)


class ValidateIn(BaseModel):
    idea: str = Field(min_length=10, max_length=2000)


@app.post("/discover", dependencies=[Depends(limit("runs"))])
def discover(b: DiscoverIn, uid: str = Depends(user)):
    prof = fwd("GET", f"{PROFILE}/profiles/{uid}")
    return fwd("POST", f"{U['orchestrator']}/discover", json={"profile": prof, **b.model_dump()})


@app.post("/validate", dependencies=[Depends(limit("runs"))])
def validate(b: ValidateIn, uid: str = Depends(user)):
    rail = fwd("POST", f"{U['critic']}/rail", json={"text": b.idea})
    if not rail["ok"]:
        raise HTTPException(422, rail["message"])
    prof = fwd("GET", f"{PROFILE}/profiles/{uid}")
    try:  # cache hit is visible to the user
        hit = fwd("GET", f"{PROFILE}/cache/verdict", params={"idea": b.idea, "user_id": uid, "rubric_set": RUBRIC_SET})
        metrics.inc("verdict_cache_hits_total")
        return {"run_id": hit.get("run_id"), "cached": True, "result": hit}
    except HTTPException:
        pass
    return fwd("POST", f"{U['orchestrator']}/validate", json={"idea": b.idea, "profile": prof})


@app.get("/runs/{run_id}", dependencies=[Depends(limit("default"))])
def run(run_id: str, uid: str = Depends(user)):
    return fwd("GET", f"{U['orchestrator']}/runs/{run_id}")


@app.get("/runs/{run_id}/events")
def run_events(run_id: str, token: str):
    """SSE. EventSource cannot send headers, so the token comes as a query param."""
    if not read_token(token):
        raise HTTPException(401)

    def stream():
        with httpx.stream("GET", f"{U['orchestrator']}/runs/{run_id}/events", timeout=None) as r:
            for chunk in r.iter_text():
                yield chunk
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/runs/{run_id}/trace", dependencies=[Depends(limit("default"))])
def run_trace(run_id: str, uid: str = Depends(user)):
    return fwd("GET", f"{U['agentops']}/runs/{run_id}/trace")


class AnswerIn(BaseModel):
    answers: dict[str, str]


@app.post("/runs/{run_id}/answer", dependencies=[Depends(limit("default"))])
def answer(run_id: str, b: AnswerIn, uid: str = Depends(user)):
    return fwd("POST", f"{U['orchestrator']}/runs/{run_id}/answer", json=b.model_dump())


class ApproveIn(BaseModel):
    approve: bool


@app.post("/runs/{run_id}/approve", dependencies=[Depends(limit("default"))])
def approve(run_id: str, b: ApproveIn, uid: str = Depends(user)):
    return fwd("POST", f"{U['orchestrator']}/runs/{run_id}/approve", json=b.model_dump())


# ---------------------------------------------------------------- ideas
class ChallengeIn(BaseModel):
    run_id: str
    card: dict
    dimension: str


@app.post("/ideas/{idea_id}/challenge", dependencies=[Depends(limit("runs"))])
def challenge(idea_id: str, b: ChallengeIn, uid: str = Depends(user)):
    prof = fwd("GET", f"{PROFILE}/profiles/{uid}")
    return fwd("POST", f"{U['orchestrator']}/ideas/challenge", json={**b.model_dump(), "profile": prof})


class WhatIfIn(BaseModel):
    run_id: str
    idea: str
    card: dict
    apply_text: str = ""   # empty => propose; filled => apply and create version N+1


@app.post("/ideas/{idea_id}/whatif", dependencies=[Depends(limit("runs"))])
def whatif(idea_id: str, b: WhatIfIn, uid: str = Depends(user)):
    if not b.apply_text:
        return fwd("POST", f"{U['orchestrator']}/ideas/whatif/propose",
                   json={"run_id": b.run_id, "idea": b.idea, "card": b.card})
    prof = fwd("GET", f"{PROFILE}/profiles/{uid}")
    return fwd("POST", f"{U['orchestrator']}/ideas/whatif/apply",
               json={"idea_id": idea_id, "version": b.card.get("version", 1),
                     "new_idea_text": b.apply_text, "profile": prof})


@app.get("/ideas", dependencies=[Depends(limit("default"))])
def ideas(uid: str = Depends(user)):
    return fwd("GET", f"{PROFILE}/ideas", params={"user_id": uid})


@app.get("/ideas/{idea_id}/versions", dependencies=[Depends(limit("default"))])
def versions(idea_id: str, uid: str = Depends(user)):
    return fwd("GET", f"{PROFILE}/ideas/{idea_id}/versions")


@app.get("/compare", dependencies=[Depends(limit("default"))])
def compare(a: str, b: str, uid: str = Depends(user)):
    return fwd("GET", f"{PROFILE}/compare", params={"a": a, "b": b})
