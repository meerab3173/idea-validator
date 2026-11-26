"""Service layer: business rules, no SQL. Unit-tested with in-memory repos."""
from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from common.schemas import DIMENSIONS, StudentProfile

CACHE_TTL = 24 * 3600


def cache_key(idea_text: str, profile_version: int, user_id: str, rubric_set: str, weights_version: str) -> str:
    """Cache keys include profile AND rubric versions (Guide, common mistakes):
    a profile edit or a rubric change can never serve an old verdict."""
    h = hashlib.sha256(" ".join(idea_text.lower().split()).encode()).hexdigest()[:16]
    return f"verdict:{h}:u{user_id}:p{profile_version}:{rubric_set}:{weights_version}"


class ProfileService:
    def __init__(self, profiles, users=None):
        self.profiles, self.users = profiles, users

    def get(self, user_id: str) -> dict:
        p = self.profiles.get(user_id)
        if p is None:
            p = self.profiles.upsert(StudentProfile(user_id=user_id, hours_per_week=10, weeks_available=12,
                                                    team_size=1).model_dump())
        return p

    def update(self, user_id: str, data: dict) -> dict:
        p = StudentProfile(**{**data, "user_id": user_id})  # validates input
        return self.profiles.upsert(p.model_dump())


class UserService:
    def __init__(self, users):
        self.users = users

    def create(self, email: str, password_hash: str) -> dict:
        email = email.strip().lower()
        if self.users.by_email(email):
            raise ValueError("email already registered")
        uid = f"u_{uuid.uuid4().hex[:8]}"
        self.users.create(uid, email.lower(), password_hash)
        return {"id": uid, "email": email.lower()}

    def by_email(self, email: str) -> Optional[dict]:
        return self.users.by_email(email.lower())


class IdeaService:
    def __init__(self, ideas, cache, weights_version: str = "w1"):
        self.ideas, self.cache, self.wv = ideas, cache, weights_version

    def save_verdict(self, payload: dict, profile_version: int) -> None:
        card = payload["card"]
        self.ideas.save_verdict(payload.get("user_id"), payload["idea_id"], payload["version"],
                                payload["idea_text"], card, payload["run_id"], payload.get("rubric_set", ""),
                                payload.get("source", "own"))
        key = cache_key(payload["idea_text"], profile_version, payload.get("user_id", ""),
                        payload.get("rubric_set", ""), self.wv)
        self.cache.set(key, card, CACHE_TTL)

    def cached_verdict(self, idea_text: str, user_id: str, profile_version: int, rubric_set: str) -> Optional[dict]:
        hit = self.cache.get(cache_key(idea_text, profile_version, user_id, rubric_set, self.wv))
        return {**hit, "cache_hit": True} if hit else None

    def compare(self, a: str, b: str) -> dict:
        ca, cb = self.ideas.latest_card(a), self.ideas.latest_card(b)
        if not ca or not cb:
            raise KeyError("both ideas need a verdict")
        sa = {s["dimension"]: s["score"] for s in ca["scores"]}
        sb = {s["dimension"]: s["score"] for s in cb["scores"]}
        return {"a": {"idea_id": a, "verdict": ca["verdict"], "score": ca.get("score")},
                "b": {"idea_id": b, "verdict": cb["verdict"], "score": cb.get("score")},
                "dimensions": [{"dimension": d, "a": sa.get(d), "b": sb.get(d),
                                "better": "a" if (sa.get(d) or 0) > (sb.get(d) or 0) else
                                          "b" if (sb.get(d) or 0) > (sa.get(d) or 0) else "tie"}
                               for d in DIMENSIONS]}
