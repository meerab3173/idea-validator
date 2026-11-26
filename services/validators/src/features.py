"""Computed features (numbers calculated in code, not by a model) and the
gate inputs for M11. Each scorer = own rubric + own tools + own features."""
from __future__ import annotations

import re

from common.text import tokenize

VOICE = {"reddit", "hackernews"}
PRODUCT = {"github", "yc", "producthunt"}

# Effort model (hours) for the feasibility gate. Documented in a decision record;
# tune it against your labelled set.
BASE_HOURS = 40
COMPONENTS = {
    r"\b(login|auth|account|sign ?up)\b": 15,
    r"\b(payment|stripe|checkout|subscription|billing)\b": 30,
    r"\b(real.?time|chat|live|websocket|multiplayer)\b": 35,
    r"\b(mobile|android|ios|flutter|react native)\b": 50,
    r"\b(ml|machine learning|model|classif\w*|predict\w*|recommend\w*|ai|llm|rag)\b": 45,
    r"\b(scrap\w*|crawl\w*|integrat\w*|api)\b": 20,
    r"\b(marketplace|two.?sided|buyers? and sellers?)\b": 60,
    r"\b(map|location|gps|geo)\b": 20,
    r"\b(video|stream\w*|audio|speech|voice)\b": 40,
    r"\b(hardware|iot|sensor|robot\w*|arduino)\b": 70,
    r"\b(dashboard|analytics|report\w*)\b": 15,
    r"\b(admin|roles?|permissions?)\b": 10,
}
SKILL_NEEDS = {
    "react": r"\b(web|dashboard|frontend|ui)\b", "python": r"\b(ml|ai|model|scrap\w*|data)\b",
    "flutter": r"\b(mobile|android|ios)\b", "sql": r"\b(database|records|history|track\w*)\b",
    "ml": r"\b(ml|machine learning|predict\w*|classif\w*|recommend\w*|llm|rag|ai)\b",
    "devops": r"\b(deploy\w*|kubernetes|cloud)\b",
}
RISK_BLOCKERS = {
    r"\b(bypass\w* (a )?paywall|piracy|torrent\w* movies)\b": "copyright infringement",
    r"\b(scrape|scraping) (linkedin|facebook|instagram)\b": "violates platform terms (scraping)",
    r"\b(gambling|betting)\b": "gambling is illegal in Pakistan",
    r"\b(surveil\w*|track\w* (my |your )?(partner|spouse|employees' phones))\b": "covert surveillance",
}
RISK_CONCERNS = {
    r"\b(health|medical|patient|clinic|therapy|mental)\b": "health data",
    r"\b(bank|loan|payment|wallet|finance)\b": "financial data",
    r"\b(child\w*|kids|minor|school students)\b": "minors",
    r"\b(location|gps|personal data|cnic|identity)\b": "personal data",
    r"\b(reddit|twitter|x\.com|instagram|tiktok) api\b": "single-platform dependency",
}


def _rx(pat: str) -> re.Pattern:
    """Allow simple plurals: 'payment' also matches 'payments'."""
    return re.compile(pat[:-2] + r"s?\b" if pat.endswith(")\\b") else pat, re.I)


def estimate_hours(idea: str) -> tuple[float, list[str]]:
    t = idea.lower()
    hours, parts = BASE_HOURS, ["base app"]
    for pat, h in COMPONENTS.items():
        if _rx(pat).search(t):
            hours += h
            parts.append(pat.strip("\\b()").split("|")[0])
    return float(hours), parts


def demand_features(evidence: list[dict], niche_slope: float = 0.0) -> dict:
    voice = [e for e in evidence if e["source"] in VOICE]
    complaint = re.compile(r"\b(slow|wish|missing|hate|can't|cannot|struggl|frustrat|lack|expensive|annoy)", re.I)
    return {"n_sources": len({e["card_id"] for e in evidence}),
            "n_voice_sources": len({e["card_id"] for e in voice}),
            "n_platforms": len({e["source"] for e in evidence}),
            "complaint_count": sum(bool(complaint.search(e.get("quote", ""))) for e in voice),
            "trend_growth": round(niche_slope, 3)}


def idea_overlap(idea: str, text: str) -> float:
    a, b = set(tokenize(idea)), set(tokenize(text))
    return len(a & b) / max(1, len(a))


def competition_features(idea: str, evidence: list[dict], dup_threshold: float = 0.6) -> dict:
    prods = [e for e in evidence if e["source"] in PRODUCT]
    ov = sorted(((idea_overlap(idea, e.get("quote", "")), e) for e in prods), key=lambda x: -x[0])
    direct = [e for o, e in ov if o >= 0.3]
    dup = ov[0][1] if ov and ov[0][0] >= dup_threshold else None
    return {"n_direct_competitors": len(direct),
            "competitor_ids": [e["card_id"] for e in direct][:5],
            "top_overlap": round(ov[0][0], 2) if ov else 0.0,
            "duplicate_of": (dup.get("name") or dup["card_id"]) if dup else None}


def feasibility_features(idea: str, profile: dict) -> dict:
    est, parts = estimate_hours(idea)
    avail = profile["hours_per_week"] * profile["weeks_available"] * profile["team_size"]
    t = idea.lower()
    needed = [s for s, pat in SKILL_NEEDS.items() if re.search(pat, t)]
    have = {s.lower() for s in profile.get("skills", [])}
    overlap = [s for s in needed if s in have]
    return {"estimated_hours": est, "components": parts, "available_hours": avail,
            "hours_ratio": round(est / avail, 2) if avail else 99.0,
            "skills_needed": needed, "skill_overlap": round(len(overlap) / max(1, len(needed)), 2),
            "compute_need": "gpu" if re.search(r"\b(train\w*|fine.?tun\w*|video)\b", t) else "cpu",
            "compute_have": profile.get("compute", "laptop")}


def risk_features(idea: str) -> dict:
    t = idea.lower()
    return {"blockers": [v for p, v in RISK_BLOCKERS.items() if _rx(p).search(t)],
            "concerns": sorted({v for p, v in RISK_CONCERNS.items() if _rx(p).search(t)})}


def learning_features(idea: str, profile: dict) -> dict:
    t = idea.lower()
    needed = [s for s, pat in SKILL_NEEDS.items() if re.search(pat, t)]
    wanted = {s.lower() for s in profile.get("interests", [])} | {"devops", "ml"}
    have = {s.lower() for s in profile.get("skills", [])}
    return {"new_skills": [s for s in needed if s not in have],
            "wanted_skill_overlap": len([s for s in needed if s in wanted]),
            "demo_ready": not re.search(r"\b(hardware|robot)\b", t)}
