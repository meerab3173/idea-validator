"""M2 routes layer (internal service; the gateway is the public entrance)."""
from __future__ import annotations

import os

import psycopg
from fastapi import HTTPException
from pydantic import BaseModel

from common.app import create_app

from .migrate import migrate
from .repositories import DSN, PgIdeas, PgProfiles, PgUsers, RedisCache
from .services import IdeaService, ProfileService, UserService

conn = None
S: dict = {}


async def ready() -> bool:
    try:
        conn.execute("SELECT 1")
        S["cache"].r.ping()
        return True
    except Exception:
        return False


app, metrics = create_app("profile", ready)


@app.on_event("startup")
def startup():
    global conn
    conn = psycopg.connect(DSN, autocommit=True)
    migrate(conn)
    cache = RedisCache()
    S.update(cache=cache, users=UserService(PgUsers(conn)), profiles=ProfileService(PgProfiles(conn)),
             ideas=IdeaService(PgIdeas(conn), cache, os.environ.get("WEIGHTS_VERSION", "w1")))


class NewUser(BaseModel):
    email: str
    password_hash: str


@app.post("/users")
def create_user(b: NewUser):
    try:
        return S["users"].create(b.email, b.password_hash)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/users/by-email/{email}")
def user_by_email(email: str):
    u = S["users"].by_email(email)
    if not u:
        raise HTTPException(404)
    return u


@app.get("/profiles/{user_id}")
def get_profile(user_id: str):
    return S["profiles"].get(user_id)


@app.put("/profiles/{user_id}")
def put_profile(user_id: str, body: dict):
    try:
        return S["profiles"].update(user_id, body)
    except Exception as e:  # pydantic validation
        raise HTTPException(422, str(e))


@app.post("/internal/save/verdict")
def save_verdict(body: dict):
    p = S["profiles"].get(body.get("user_id", ""))
    S["ideas"].save_verdict(body, p.get("version", 1))
    return {"ok": True}


@app.post("/internal/save/discover")
def save_discover(body: dict):
    conn.execute("INSERT INTO runs (run_id,user_id,kind,status,result) VALUES (%s,%s,'discover','DONE',%s) "
                 "ON CONFLICT DO NOTHING", (body["run_id"], body["profile"].get("user_id"),
                                             psycopg.types.json.Jsonb(body["result"])))
    return {"ok": True}


@app.get("/cache/verdict")
def cached(idea: str, user_id: str, rubric_set: str):
    p = S["profiles"].get(user_id)
    hit = S["ideas"].cached_verdict(idea, user_id, p["version"], rubric_set)
    metrics.inc("cache_requests_total", hit=str(bool(hit)).lower())
    if not hit:
        raise HTTPException(404, "miss")
    return hit


@app.get("/ideas")
def ideas(user_id: str):
    return S["ideas"].ideas.list_ideas(user_id)


@app.get("/ideas/{idea_id}/versions")
def versions(idea_id: str):
    return S["ideas"].ideas.versions(idea_id)


@app.get("/compare")
def compare(a: str, b: str):
    try:
        return S["ideas"].compare(a, b)
    except KeyError as e:
        raise HTTPException(404, str(e))
