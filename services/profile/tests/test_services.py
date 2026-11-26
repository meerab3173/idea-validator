import pytest

from src.services import IdeaService, ProfileService, UserService, cache_key


class MemProfiles:
    def __init__(self): self.d = {}
    def get(self, uid): return self.d.get(uid)

    def upsert(self, p):
        v = self.d.get(p["user_id"], {}).get("version", 0) + 1
        self.d[p["user_id"]] = {**p, "version": v}
        return self.d[p["user_id"]]


class MemUsers:
    def __init__(self): self.d = {}
    def create(self, uid, email, h): self.d[email] = {"id": uid, "email": email, "hash": h}
    def by_email(self, email): return self.d.get(email)


class MemIdeas:
    def __init__(self): self.cards = {}
    def save_verdict(self, user_id, idea_id, version, text, card, run_id, rubric_set, source): self.cards[idea_id] = card
    def latest_card(self, idea_id): return self.cards.get(idea_id)


class MemCache:
    def __init__(self): self.d = {}
    def get(self, k): return self.d.get(k)
    def set(self, k, v, ttl): self.d[k] = v


def test_profile_update_bumps_version_and_validates():
    s = ProfileService(MemProfiles())
    p1 = s.update("u1", {"hours_per_week": 10, "weeks_available": 12, "team_size": 2})
    p2 = s.update("u1", {"hours_per_week": 5, "weeks_available": 12, "team_size": 2})
    assert p2["version"] == p1["version"] + 1
    with pytest.raises(Exception):
        s.update("u1", {"hours_per_week": -3, "weeks_available": 12, "team_size": 2})


def test_duplicate_email_rejected():
    u = UserService(MemUsers())
    u.create("a@b.com", "h")
    with pytest.raises(ValueError):
        u.create("A@b.com", "h")


def test_cache_key_contains_profile_and_rubric_versions():
    k = cache_key("My Idea", 3, "u1", "r2", "w1")
    assert ":p3:" in k and ":r2:" in k and k == cache_key("  my   idea ", 3, "u1", "r2", "w1")
    assert k != cache_key("My Idea", 4, "u1", "r2", "w1") != cache_key("My Idea", 3, "u1", "r3", "w1")


def test_cache_hit_visible_and_invalidated_by_profile_change():
    s = IdeaService(MemIdeas(), MemCache())
    card = {"verdict": "GO", "scores": []}
    s.save_verdict({"user_id": "u1", "idea_id": "i1", "version": 1, "idea_text": "x idea",
                    "card": card, "run_id": "r", "rubric_set": "r1"}, profile_version=1)
    assert s.cached_verdict("x idea", "u1", 1, "r1")["cache_hit"] is True
    assert s.cached_verdict("x idea", "u1", 2, "r1") is None   # profile edited
    assert s.cached_verdict("x idea", "u1", 1, "r2") is None   # rubric changed


def test_compare_six_dimensions():
    ideas = MemIdeas()
    mk = lambda v: {"verdict": "GO", "score": 70, "scores": [{"dimension": d, "score": v} for d in
                    ["demand_pain", "competition", "differentiation", "feasibility", "risk", "learning"]]}
    ideas.cards = {"a": mk(4), "b": mk(3)}
    c = IdeaService(ideas, MemCache()).compare("a", "b")
    assert len(c["dimensions"]) == 6 and all(d["better"] == "a" for d in c["dimensions"])
