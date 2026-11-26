"""M9: four scorer agents run in parallel. Each retrieves its own evidence
(own tools), computes its features, then asks M10 to apply its rubric."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from common.schemas import GateInputs

from .features import (competition_features, demand_features, feasibility_features,
                       learning_features, risk_features)

Search = Callable[[str, dict], list[dict]]          # (query, filters) -> evidence
Score = Callable[[str, str, list[dict], dict, dict], dict]  # (dim, idea, evidence, profile, features) -> DimensionScore dict


def demand_agent(idea, profile, search: Search, score: Score, niche_slope=0.0):
    ev = search(f"{idea} problem complaint", {"source": ["reddit", "hackernews"]}) + \
         search(idea, {})
    ev = list({e["evidence_id"]: e for e in ev}.values())
    f = demand_features(ev, niche_slope)
    return {"scores": [score("demand_pain", idea, ev, profile, f)], "evidence": ev, "features": f}


def competition_agent(idea, profile, search: Search, score: Score):
    ev = search(idea, {"source": ["github", "yc", "producthunt"]}) + search(f"{idea} alternative", {})
    ev = list({e["evidence_id"]: e for e in ev}.values())
    f = competition_features(idea, ev)
    return {"scores": [score("competition", idea, ev, profile, f),
                       score("differentiation", idea, ev, profile, f)], "evidence": ev, "features": f}


def feasibility_agent(idea, profile, search: Search, score: Score):
    ev = search(f"{idea} open source implementation", {"source": ["github"]})
    f = feasibility_features(idea, profile)
    lf = learning_features(idea, profile)
    return {"scores": [score("feasibility", idea, ev, profile, f),
                       score("learning", idea, ev, profile, lf)], "evidence": ev, "features": {**f, **lf}}


def risk_agent(idea, profile, search: Search, score: Score):
    ev = search(f"{idea} privacy legal terms ban", {})
    f = risk_features(idea)
    return {"scores": [score("risk", idea, ev, profile, f)], "evidence": ev, "features": f}


def run_all(idea: str, profile: dict, search: Search, score: Score, niche_slope: float = 0.0,
            timeout: float = 120) -> dict:
    """Run the four agents in parallel; a failed agent leaves its dimensions
    missing, so M11 returns INSUFFICIENT_EVIDENCE for them instead of guessing."""
    jobs = {
        "demand": lambda: demand_agent(idea, profile, search, score, niche_slope),
        "competition": lambda: competition_agent(idea, profile, search, score),
        "feasibility": lambda: feasibility_agent(idea, profile, search, score),
        "risk": lambda: risk_agent(idea, profile, search, score),
    }
    results, errors = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {k: pool.submit(f) for k, f in jobs.items()}
        for k, fut in futs.items():
            try:
                results[k] = fut.result(timeout=timeout)
            except Exception as e:  # noqa: BLE001
                errors[k] = repr(e)
    scores = [s for r in results.values() for s in r["scores"]]
    evidence = list({e["evidence_id"]: e for r in results.values() for e in r["evidence"]}.values())
    feats = {k: r["features"] for k, r in results.items()}
    d = feats.get("demand", {})
    gates = GateInputs(
        n_sources=len({e["card_id"] for e in evidence}),
        n_platforms=len({e["source"] for e in evidence}),
        estimated_hours=feats.get("feasibility", {}).get("estimated_hours", 0),
        blockers=feats.get("risk", {}).get("blockers", []),
        duplicate_of=feats.get("competition", {}).get("duplicate_of"),
    )
    # Evidence gate counts only sources that the scorers actually cited.
    cited = {i for s in scores for i in s.get("evidence_ids", [])}
    cited_ev = [e for e in evidence if e["evidence_id"] in cited]
    if cited_ev:
        gates.n_sources = len({e["card_id"] for e in cited_ev})
        gates.n_platforms = len({e["source"] for e in cited_ev})
    return {"scores": scores, "evidence": evidence, "features": feats, "gates": gates.model_dump(),
            "errors": errors, "demand": d}
