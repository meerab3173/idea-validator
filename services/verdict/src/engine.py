"""M11 Verdict Engine.

Plain code, no LLM. Same input -> same output. Rules come from
config/verdict.yaml (a ConfigMap in Kubernetes). Implements Description
Section 5: hard gates -> weighted score -> confidence -> thresholds ->
sensitivity -> what-would-make-GO, plus the challenge penalty.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from common.schemas import (
    DIMENSIONS,
    FLOOR_DIMENSIONS,
    DimensionScore,
    GateInputs,
    StudentProfile,
    Verdict,
    VerdictResult,
    WhatIf,
)

EPS = 1e-9


@dataclass(frozen=True)
class EngineConfig:
    raw: dict

    @property
    def thresholds(self) -> dict:
        return self.raw["thresholds"]

    def weights_for(self, goal: str) -> dict[str, float]:
        w = {k: float(v) for k, v in self.raw["weights"][goal].items()}
        if abs(sum(w.values()) - 100) > 1e-6:
            raise ValueError(f"weights for {goal} must add to 100")
        return w


# ------------------------------------------------------------------ helpers
def weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Sum of weight x score, scaled to 0-100 (scores 0-5, weights add to 100)."""
    return sum(weights[d] * scores[d] for d in DIMENSIONS) / 5.0


def overall_confidence(dims: list[DimensionScore], n_sources: int, cfg: dict) -> float:
    c = cfg["confidence"]
    mean_conf = sum(d.confidence for d in dims) / len(dims)
    src = min(1.0, n_sources / c["sources_for_full"])
    return round(c["w_mean_conf"] * mean_conf + c["w_sources"] * src, 4)


def shift_weight(weights: dict[str, float], dim: str, factor: float) -> dict[str, float]:
    """Move one weight by `factor` (e.g. 0.8 or 1.2) and share the difference
    among the others in proportion to their size, so the total stays 100."""
    new = dict(weights)
    old = weights[dim]
    new[dim] = old * factor
    diff = old - new[dim]  # positive => freed points to give away
    others = [d for d in DIMENSIONS if d != dim]
    total_others = sum(weights[d] for d in others)
    for d in others:
        new[d] = weights[d] + diff * (weights[d] / total_others)
    return new


def weakest_dimension(scores: dict[str, float], weights: dict[str, float]) -> str:
    # Lowest score; tie -> the one with the bigger weight (it hurts more).
    return min(DIMENSIONS, key=lambda d: (scores[d], -weights[d]))


# ------------------------------------------------------------------ gates
def check_gates(
    g: GateInputs, profile: StudentProfile, scores: dict[str, float], cfg: dict
) -> tuple[dict[str, str], dict[str, str]]:
    gc = cfg["gates"]
    gates: dict[str, str] = {}
    msgs: dict[str, str] = {}

    ok = g.n_sources >= gc["evidence_min_sources"] and g.n_platforms >= gc["evidence_min_platforms"]
    gates["evidence"] = "pass" if ok else "fail"
    if not ok:
        msgs["evidence"] = (
            f"Found {g.n_sources} independent sources on {g.n_platforms} platforms; "
            f"need {gc['evidence_min_sources']}+ sources on {gc['evidence_min_platforms']}+ platforms."
        )

    avail = profile.available_hours
    ok = g.estimated_hours <= avail
    gates["feasibility"] = "pass" if ok else "fail"
    if not ok:
        msgs["feasibility"] = (
            f"Estimated {g.estimated_hours:.0f} h of work but only {avail:.0f} h available "
            f"(gap {g.estimated_hours - avail:.0f} h)."
        )

    ok = not g.blockers
    gates["risk"] = "pass" if ok else "fail"
    if not ok:
        msgs["risk"] = "Blocker: " + "; ".join(g.blockers)

    override = scores["differentiation"] >= gc["duplicate_differentiation_override"]
    ok = g.duplicate_of is None or override
    gates["duplicate"] = "pass" if ok else "fail"
    if not ok:
        msgs["duplicate"] = f"Same core features for the same user as existing product: {g.duplicate_of}."
    return gates, msgs


# ------------------------------------------------------------------ core decision
@dataclass
class Decision:
    verdict: Verdict
    score: Optional[float]
    gates: dict[str, str]
    gate_messages: dict[str, str]
    weakest: Optional[str]
    reason: str
    missing: list[str]


def decide(
    scores: dict[str, float],
    confidence: float,
    gates_in: GateInputs,
    profile: StudentProfile,
    weights: dict[str, float],
    cfg: dict,
) -> Decision:
    gates, msgs = check_gates(gates_in, profile, scores, cfg)
    t = cfg["thresholds"]

    # Gates first, in fixed order. A failed gate decides the verdict.
    if gates["evidence"] == "fail":
        return Decision(Verdict.INSUFFICIENT_EVIDENCE, None, gates, msgs, None,
                        msgs["evidence"], [msgs["evidence"]])
    for g in ("feasibility", "risk", "duplicate"):
        if gates[g] == "fail":
            return Decision(Verdict.NO_GO, None, gates, msgs, None, msgs[g], [])

    score = round(weighted_score(scores, weights), 2)
    weakest = weakest_dimension(scores, weights)

    if confidence < cfg["confidence"]["min"] - EPS:
        m = f"Overall confidence {confidence:.2f} is below {cfg['confidence']['min']}."
        return Decision(Verdict.INSUFFICIENT_EVIDENCE, score, gates, msgs, weakest, m, [m])

    floor_breach = [d for d in FLOOR_DIMENSIONS if scores[d] < t["floor"] - EPS]
    if score >= t["T_go"] - EPS and not floor_breach:
        return Decision(Verdict.GO, score, gates, msgs, weakest,
                        f"Score {score} >= {t['T_go']} and no dimension below the floor.", [])
    if score >= t["T_no"] - EPS:
        why = (f"{', '.join(floor_breach)} below floor {t['floor']}" if floor_breach
               else f"score {score} between {t['T_no']} and {t['T_go']}")
        return Decision(Verdict.PIVOT, score, gates, msgs, weakest,
                        f"PIVOT: {why}. Weakest dimension: {weakest}.", [])
    return Decision(Verdict.NO_GO, score, gates, msgs, weakest,
                    f"Score {score} is below {t['T_no']}.", [])


# ------------------------------------------------------------------ sensitivity
def sensitivity(
    scores: dict[str, float], dims: list[DimensionScore], confidence: float,
    gates_in: GateInputs, profile: StudentProfile, weights: dict[str, float],
    cfg: dict, base: Verdict,
) -> dict:
    s = cfg["sensitivity"]
    runs, flips = 0, []
    for d in DIMENSIONS:
        for factor in (1 - s["weight_delta"], 1 + s["weight_delta"]):
            w2 = shift_weight(weights, d, factor)
            r = decide(scores, confidence, gates_in, profile, w2, cfg)
            runs += 1
            if r.verdict != base:
                flips.append({"change": f"weight {d} x{factor:.2f} ({weights[d]:.0f} -> {w2[d]:.1f})",
                              "new_score": r.score, "new_verdict": r.verdict.value})
    least = min(dims, key=lambda x: (x.confidence, DIMENSIONS.index(x.dimension))).dimension
    for delta in (-s["score_delta"], s["score_delta"]):
        sc2 = dict(scores)
        sc2[least] = min(5.0, max(0.0, sc2[least] + delta))
        r = decide(sc2, confidence, gates_in, profile, weights, cfg)
        runs += 1
        if r.verdict != base:
            flips.append({"change": f"{least} score {scores[least]} -> {sc2[least]}",
                          "new_score": r.score, "new_verdict": r.verdict.value})
    return {"runs": runs, "flipped": len(flips), "flips": flips, "least_confident": least}


def is_stable(scores, dims, confidence, gates_in, profile, weights, cfg, verdict) -> bool:
    return sensitivity(scores, dims, confidence, gates_in, profile, weights, cfg, verdict)["flipped"] == 0


# ------------------------------------------------------------------ what would make GO
def what_would_make_go(
    scores: dict[str, float], dims: list[DimensionScore], confidence: float,
    gates_in: GateInputs, profile: StudentProfile, weights: dict[str, float], cfg: dict,
    current: Verdict,
) -> list[WhatIf]:
    """Smallest single change that turns the verdict into GO. One entry per
    dimension (minimal raise), sorted by size of change; stable GOs first on ties."""
    out: list[WhatIf] = []
    gates, _ = check_gates(gates_in, profile, scores, cfg)

    if gates["evidence"] == "fail":
        return []  # cannot reason without evidence: do not guess (U10)
    if gates["feasibility"] == "fail":
        cut = gates_in.estimated_hours - profile.available_hours
        out.append(WhatIf(change=f"Cut scope by about {cut:.0f} hours (or add hours / a team member)",
                          new_verdict="re-run needed"))
        return out
    if gates["risk"] == "fail":
        out.append(WhatIf(change="Remove the blocker: " + "; ".join(gates_in.blockers),
                          new_verdict="re-run needed"))
        return out

    step = cfg["whatif"]["step"]
    for d in DIMENSIONS:
        v = scores[d]
        target = v
        while target < 5.0 - EPS:
            target = round(min(5.0, target + step), 2)
            sc2 = dict(scores)
            sc2[d] = target
            r = decide(sc2, confidence, gates_in, profile, weights, cfg)
            if r.verdict == Verdict.GO:
                stable = is_stable(sc2, dims, confidence, gates_in, profile, weights, cfg, Verdict.GO)
                # Already GO but BORDERLINE => the goal is a *stable* GO.
                if current == Verdict.GO and not stable:
                    continue
                out.append(WhatIf(change=f"Raise {d} from {v} to {target}", dimension=d,
                                  from_score=v, to_score=target, new_score=r.score,
                                  new_verdict="GO", stable=stable))
                break
    out.sort(key=lambda w: (round(w.to_score - w.from_score, 2), not w.stable, -weights[w.dimension]))
    return out


# ------------------------------------------------------------------ challenge
def apply_challenge(dims: list[DimensionScore], accepted: dict[str, int], cfg: dict) -> list[DimensionScore]:
    """Each objection the critic accepted lowers the matching score by 0.5
    (at most 1.0 in total) and its confidence by 0.1."""
    c = cfg["challenge"]
    out = []
    for d in dims:
        n = accepted.get(d.dimension, 0)
        if n <= 0:
            out.append(d)
            continue
        penalty = min(c["max_penalty"], n * c["score_penalty"])
        n_eff = round(penalty / c["score_penalty"])
        out.append(d.model_copy(update={
            "score": max(0.0, d.score - penalty),
            "confidence": max(0.0, round(d.confidence - n_eff * c["confidence_penalty"], 4)),
        }))
    return out


# ------------------------------------------------------------------ public entry
def evaluate(
    dims: list[DimensionScore], profile: StudentProfile, gates_in: GateInputs, cfg: dict,
    idea_id: str = "", version: int = 1, run_id: str = "", rubric_version: str = "",
) -> VerdictResult:
    by = {d.dimension: d for d in dims}
    missing_dims = [d for d in DIMENSIONS if d not in by]
    abstained = [d.dimension for d in dims if d.abstained]
    weights = EngineConfig(cfg).weights_for(profile.goal)
    t = cfg["thresholds"]
    versions = {"engine": cfg.get("engine_version", "m11@v1"),
                "rubrics": rubric_version, "profile_weights": cfg.get("version", "")}

    if missing_dims or abstained:
        miss = [f"No evidence-backed score for {d} (scorer abstained)." for d in missing_dims + abstained]
        return VerdictResult(idea_id=idea_id, version=version, run_id=run_id,
                             verdict=Verdict.INSUFFICIENT_EVIDENCE, confidence=0.0,
                             gates={"evidence": "fail", "feasibility": "skipped",
                                    "risk": "skipped", "duplicate": "skipped"},
                             weights=weights, thresholds=t, scores=dims, missing=miss,
                             reason="Missing dimension scores.", versions=versions)

    scores = {d: float(by[d].score) for d in DIMENSIONS}
    ordered = [by[d] for d in DIMENSIONS]
    conf = overall_confidence(ordered, gates_in.n_sources, cfg)
    dec = decide(scores, conf, gates_in, profile, weights, cfg)

    sens, wm = {"runs": 0, "flipped": 0, "flips": []}, []
    stability = "STABLE"
    if dec.verdict != Verdict.INSUFFICIENT_EVIDENCE and dec.score is not None:
        sens = sensitivity(scores, ordered, conf, gates_in, profile, weights, cfg, dec.verdict)
        stability = "BORDERLINE" if sens["flipped"] else "STABLE"
    if dec.verdict != Verdict.GO or stability == "BORDERLINE":
        wm = what_would_make_go(scores, ordered, conf, gates_in, profile, weights, cfg, dec.verdict)

    return VerdictResult(
        idea_id=idea_id, version=version, run_id=run_id, verdict=dec.verdict,
        stability=stability, score=dec.score, confidence=conf, gates=dec.gates,
        gate_messages=dec.gate_messages, weights=weights, thresholds=t, scores=ordered,
        weakest_dimension=dec.weakest, reason=dec.reason, missing=dec.missing,
        what_would_make_go=wm, sensitivity=sens, versions=versions,
    )


def apply_whatif(dims: list[DimensionScore], dimension: str, new_score: float) -> list[DimensionScore]:
    """Used by POST /whatif for a quick engine-only preview. The real version 2
    re-runs the scorers through the orchestrator, then calls evaluate()."""
    return [d.model_copy(update={"score": new_score}) if d.dimension == dimension else d for d in dims]
