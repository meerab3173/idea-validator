"""Repository layer: the ONLY place with SQL / Redis calls (layered like
Assignment 1: routes -> services -> repositories)."""
from __future__ import annotations

import json
import os
from typing import Optional, Protocol

DSN = os.environ.get("DATABASE_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


class UserRepo(Protocol):
    def create(self, uid: str, email: str, hash_: str) -> None: ...
    def by_email(self, email: str) -> Optional[dict]: ...


class ProfileRepo(Protocol):
    def get(self, user_id: str) -> Optional[dict]: ...
    def upsert(self, p: dict) -> dict: ...


class IdeaRepo(Protocol):
    def save_verdict(self, user_id: str, idea_id: str, version: int, text: str, card: dict,
                     run_id: str, rubric_set: str, source: str) -> None: ...
    def list_ideas(self, user_id: str) -> list[dict]: ...
    def versions(self, idea_id: str) -> list[dict]: ...
    def latest_card(self, idea_id: str) -> Optional[dict]: ...


class Cache(Protocol):
    def get(self, key: str) -> Optional[dict]: ...
    def set(self, key: str, value: dict, ttl: int) -> None: ...


# ---------------------------------------------------------------- Postgres
class PgUsers:
    def __init__(self, conn): self.c = conn

    def create(self, uid, email, hash_):
        self.c.execute("INSERT INTO users (id,email,hash) VALUES (%s,%s,%s)", (uid, email, hash_))

    def by_email(self, email):
        r = self.c.execute("SELECT id,email,hash FROM users WHERE email=%s", (email,)).fetchone()
        return {"id": r[0], "email": r[1], "hash": r[2]} if r else None


PROFILE_COLS = ("user_id", "skills", "hours_per_week", "weeks_available", "team_size", "compute",
                "goal", "interests", "version")


class PgProfiles:
    def __init__(self, conn): self.c = conn

    def get(self, user_id):
        r = self.c.execute(f"SELECT {','.join(PROFILE_COLS)} FROM profiles WHERE user_id=%s", (user_id,)).fetchone()
        return dict(zip(PROFILE_COLS, r)) if r else None

    def upsert(self, p):
        r = self.c.execute(
            """INSERT INTO profiles (user_id,skills,hours_per_week,weeks_available,team_size,compute,goal,interests)
               VALUES (%(user_id)s,%(skills)s,%(hours_per_week)s,%(weeks_available)s,%(team_size)s,%(compute)s,%(goal)s,%(interests)s)
               ON CONFLICT (user_id) DO UPDATE SET skills=EXCLUDED.skills, hours_per_week=EXCLUDED.hours_per_week,
                 weeks_available=EXCLUDED.weeks_available, team_size=EXCLUDED.team_size, compute=EXCLUDED.compute,
                 goal=EXCLUDED.goal, interests=EXCLUDED.interests, version=profiles.version+1, updated_at=now()
               RETURNING version""", p).fetchone()
        return {**p, "version": r[0]}


class PgIdeas:
    def __init__(self, conn): self.c = conn

    def save_verdict(self, user_id, idea_id, version, text, card, run_id, rubric_set, source="own"):
        self.c.execute("INSERT INTO ideas (id,user_id,title,source) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                       (idea_id, user_id, text[:120], source))
        self.c.execute("INSERT INTO idea_versions (idea_id,version,text) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                       (idea_id, version, text))
        vid = self.c.execute(
            """INSERT INTO verdicts (idea_id,version,run_id,verdict,stability,score,confidence,card,rubric_set)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (idea_id, version, run_id, card["verdict"], card.get("stability"), card.get("score"),
             card.get("confidence"), json.dumps(card), rubric_set)).fetchone()[0]
        for s in card.get("scores", []):
            self.c.execute("INSERT INTO dimension_scores VALUES (%s,%s,%s,%s,%s)",
                           (vid, s["dimension"], s["score"], s["confidence"], s.get("evidence_ids", [])))

    def list_ideas(self, user_id):
        rows = self.c.execute(
            """SELECT i.id, i.title, i.source, max(v.version), i.created_at,
                      (SELECT verdict FROM verdicts WHERE idea_id=i.id ORDER BY id DESC LIMIT 1)
               FROM ideas i JOIN idea_versions v ON v.idea_id=i.id WHERE i.user_id=%s
               GROUP BY i.id ORDER BY i.created_at DESC""", (user_id,)).fetchall()
        return [{"id": r[0], "title": r[1], "source": r[2], "latest_version": r[3],
                 "created_at": str(r[4]), "latest_verdict": r[5]} for r in rows]

    def versions(self, idea_id):
        rows = self.c.execute(
            """SELECT v.version, v.text, d.verdict, d.score, d.stability, d.card
               FROM idea_versions v LEFT JOIN LATERAL (SELECT * FROM verdicts WHERE idea_id=v.idea_id
               AND version=v.version ORDER BY id DESC LIMIT 1) d ON TRUE
               WHERE v.idea_id=%s ORDER BY v.version""", (idea_id,)).fetchall()
        return [{"version": r[0], "text": r[1], "verdict": r[2], "score": r[3], "stability": r[4], "card": r[5]}
                for r in rows]

    def latest_card(self, idea_id):
        r = self.c.execute("SELECT card FROM verdicts WHERE idea_id=%s ORDER BY id DESC LIMIT 1", (idea_id,)).fetchone()
        return r[0] if r else None


class RedisCache:
    def __init__(self, url=REDIS_URL):
        import redis
        self.r = redis.Redis.from_url(url)

    def get(self, key):
        v = self.r.get(key)
        return json.loads(v) if v else None

    def set(self, key, value, ttl):
        self.r.setex(key, ttl, json.dumps(value))
