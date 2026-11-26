from src.agents import run_all
from src.features import competition_features, estimate_hours, feasibility_features, risk_features

PROFILE = {"skills": ["react", "sql"], "hours_per_week": 10, "weeks_available": 12, "team_size": 2,
           "compute": "laptop", "goal": "portfolio", "interests": ["education"]}
EV = [{"evidence_id": f"card_{i}#c0", "card_id": f"card_{i}", "source": s, "quote": q, "name": n}
      for i, (s, q, n) in enumerate([
          ("reddit", "students hate clashing exam timetables", "x"),
          ("hackernews", "exam timetable clash is frustrating", "y"),
          ("github", "exam timetable clash detector for universities", "exam-timetable"),
          ("yc", "AI tutor for math", "Tutor")])]


def fake_search(q, filters):
    src = filters.get("source")
    return [e for e in EV if not src or e["source"] in src]


def fake_score(dim, idea, evidence, profile, features):
    return {"dimension": dim, "score": 3.0, "confidence": 0.7,
            "evidence_ids": [e["evidence_id"] for e in evidence[:2]], "features": features}


def test_estimate_hours_adds_components():
    h, parts = estimate_hours("A web app with login, payments and real-time chat")
    assert h == 40 + 15 + 30 + 35 and len(parts) == 4


def test_feasibility_ratio():
    f = feasibility_features("dashboard for exam clashes", PROFILE)
    assert f["available_hours"] == 240 and f["hours_ratio"] < 1


def test_duplicate_detected():
    f = competition_features("exam timetable clash detector", EV)
    assert f["duplicate_of"] == "exam-timetable"


def test_risk_blocker():
    assert risk_features("An app to bypass paywalls on news sites")["blockers"]


def test_run_all_parallel_produces_six_dims_and_gates():
    r = run_all("exam timetable clash warnings for students", PROFILE, fake_search, fake_score)
    assert sorted(s["dimension"] for s in r["scores"]) == sorted(
        ["demand_pain", "competition", "differentiation", "feasibility", "learning", "risk"])
    assert r["gates"]["n_platforms"] >= 2 and r["errors"] == {}


def test_failed_agent_leaves_dims_missing():
    def boom(dim, *a):
        if dim == "risk":
            raise TimeoutError("scorer timeout")
        return fake_score(dim, *a)
    r = run_all("exam timetable clash warnings", PROFILE, fake_search, boom)
    assert "risk" in r["errors"] and all(s["dimension"] != "risk" for s in r["scores"])
