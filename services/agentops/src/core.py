"""M13 AgenticOps core: summarise traces into dashboard numbers, and drift."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean

VERDICTS = ("GO", "PIVOT", "NO-GO", "INSUFFICIENT_EVIDENCE")


def summarise(traces: list[dict], verdicts: list[dict]) -> dict:
    by_run: dict[str, float] = defaultdict(float)
    lat: dict[str, list[int]] = defaultdict(list)
    cache_hits = cache_total = fallbacks = blocked = approvals = errors = 0
    for t in traces:
        by_run[t["run_id"].rsplit("_", 1)[0] if t["run_id"].count("_") > 1 else t["run_id"]] += t.get("cost_usd", 0)
        lat[t["agent"]].append(t.get("latency_ms", 0))
        if t.get("tool") in ("fetch", "search_kb") or t.get("kind") == "llm_call":
            cache_total += 1
            cache_hits += bool(t.get("cache_hit"))
        out = str(t.get("output", ""))
        if t.get("model") and "fallback" in out.lower():
            fallbacks += 1
        if "flagged=" in out and not out.endswith("flagged=0"):
            blocked += 1
        if '"approval_needed"' in out:
            approvals += 1
        errors += bool(t.get("error"))
    vruns = [v for v in verdicts if v.get("run_id")]
    cost_per_verdict = (sum(by_run.get(v["run_id"], 0) for v in vruns) / len(vruns)) if vruns else 0.0
    return {
        "runs": len(by_run), "verdicts": len(vruns),
        "cost_per_verdict_usd": round(cost_per_verdict, 5),
        "latency_ms_per_agent": {a: {"mean": round(mean(v)), "p95": sorted(v)[max(0, int(len(v) * .95) - 1)],
                                     "n": len(v)} for a, v in lat.items()},
        "cache_hit_rate": round(cache_hits / cache_total, 3) if cache_total else 0.0,
        "fallbacks": fallbacks, "blocked_injections": blocked, "approvals_requested": approvals,
        "errors": errors,
        "verdict_distribution": dict(Counter(v.get("verdict") for v in vruns)),
    }


def distribution(verdicts: list[str]) -> dict[str, float]:
    c = Counter(verdicts)
    n = max(1, len(verdicts))
    return {k: c.get(k, 0) / n for k in VERDICTS}


def psi(before: dict[str, float], after: dict[str, float], eps: float = 1e-4) -> float:
    """Population stability index between two verdict distributions.
    < 0.1 stable, 0.1-0.25 moderate shift, > 0.25 large shift."""
    return round(sum((a - b) * math.log((a + eps) / (b + eps))
                     for b, a in ((before[k], after[k]) for k in VERDICTS)), 4)


def drift_report(kb_stats: dict, freshness_days: dict, prev_verdicts: list[str], new_verdicts: list[str],
                 stale_after_days: int = 14) -> dict:
    b, a = distribution(prev_verdicts), distribution(new_verdicts)
    p = psi(b, a)
    stale = [s for s, d in freshness_days.items() if d is None or d > stale_after_days]
    return {
        "freshness_days": freshness_days, "stale_sources": stale,
        "cards_per_source": kb_stats.get("cards_per_source", {}), "n_niches": kb_stats.get("n_niches"),
        "verdicts_before": b, "verdicts_after": a, "psi": p,
        "status": "large shift" if p > 0.25 else "moderate shift" if p > 0.1 else "stable",
        "alerts": ([f"stale source: {s}" for s in stale] + (["verdict distribution shifted"] if p > 0.1 else [])),
    }
