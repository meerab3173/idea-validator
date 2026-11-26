"""Unit tests for every gate, threshold edge, sensitivity check and what-if
(Description, M11 'Must have')."""
import copy

import pytest
import yaml

from common.config import verdict_config_path
from common.schemas import DIMENSIONS, DimensionScore, GateInputs, StudentProfile, Verdict
from src.engine import (
    apply_challenge,
    evaluate,
    overall_confidence,
    shift_weight,
    weighted_score,
)

CFG = yaml.safe_load(open(verdict_config_path()))


def dims(values, conf=0.8):
    if isinstance(conf, (int, float)):
        conf = [conf] * 6
    return [DimensionScore(dimension=d, score=v, confidence=c, evidence_ids=[f"card_{i}#c0"])
            for i, (d, v, c) in enumerate(zip(DIMENSIONS, values, conf))]


def profile(goal="portfolio", hours=10, weeks=12, team=2):
    return StudentProfile(user_id="u1", hours_per_week=hours, weeks_available=weeks,
                          team_size=team, goal=goal)


GOOD_GATES = GateInputs(n_sources=5, n_platforms=3, estimated_hours=100)
WORKED = [3.5, 2.0, 3.0, 4.0, 3.5, 4.5]  # Section 5.4


# ---------------------------------------------------------------- config
@pytest.mark.parametrize("goal", ["startup", "portfolio", "course_project"])
def test_weights_add_to_100(goal):
    assert sum(CFG["weights"][goal].values()) == 100


def test_shift_weight_keeps_total_100():
    w = CFG["weights"]["portfolio"]
    for d in DIMENSIONS:
        for f in (0.8, 1.2):
            assert sum(shift_weight(w, d, f).values()) == pytest.approx(100)


# ---------------------------------------------------------------- worked example 5.4
def test_worked_example_score_is_70_5_go_borderline():
    r = evaluate(dims(WORKED), profile(), GOOD_GATES, CFG)
    assert r.score == 70.5
    assert r.verdict == Verdict.GO
    assert r.stability == "BORDERLINE"
    flips = [f["change"] for f in r.sensitivity["flips"]]
    assert any("feasibility" in f and "0.80" in f for f in flips)


def test_worked_example_feasibility_weight_minus_20_gives_69_9():
    w2 = shift_weight(CFG["weights"]["portfolio"], "feasibility", 0.8)
    s = dict(zip(DIMENSIONS, WORKED))
    assert weighted_score(s, w2) == pytest.approx(69.87, abs=0.01)


def test_worked_example_competition_3_is_stable_go():
    v = list(WORKED); v[1] = 3.0
    r = evaluate(dims(v), profile(), GOOD_GATES, CFG)
    assert r.score == 73.5 and r.verdict == Verdict.GO and r.stability == "STABLE"
    w2 = shift_weight(CFG["weights"]["portfolio"], "feasibility", 0.8)
    assert weighted_score(dict(zip(DIMENSIONS, v)), w2) == pytest.approx(73.1, abs=0.05)


def test_worked_example_whatif_lists_competition_plus_one():
    r = evaluate(dims(WORKED), profile(), GOOD_GATES, CFG)
    comp = [w for w in r.what_would_make_go if w.dimension == "competition"]
    assert comp and comp[0].to_score == 3.0 and comp[0].stable and comp[0].new_score == 73.5


# ---------------------------------------------------------------- gates
def test_evidence_gate_too_few_sources():
    g = GOOD_GATES.model_copy(update={"n_sources": 2})
    r = evaluate(dims(WORKED), profile(), g, CFG)
    assert r.verdict == Verdict.INSUFFICIENT_EVIDENCE and r.gates["evidence"] == "fail"
    assert r.missing and r.what_would_make_go == []


def test_evidence_gate_one_platform():
    g = GOOD_GATES.model_copy(update={"n_platforms": 1})
    assert evaluate(dims(WORKED), profile(), g, CFG).verdict == Verdict.INSUFFICIENT_EVIDENCE


def test_evidence_gate_exact_minimum_passes():
    g = GOOD_GATES.model_copy(update={"n_sources": 3, "n_platforms": 2})
    assert evaluate(dims(WORKED), profile(), g, CFG).gates["evidence"] == "pass"


def test_feasibility_gate_states_hours_gap():
    # solo, 20 h total vs 200 h idea -> NO-GO (Description section 2 example)
    p = profile(hours=2, weeks=10, team=1)
    g = GOOD_GATES.model_copy(update={"estimated_hours": 200})
    r = evaluate(dims(WORKED), p, g, CFG)
    assert r.verdict == Verdict.NO_GO and r.gates["feasibility"] == "fail"
    assert "gap 180" in r.gate_messages["feasibility"]


def test_same_idea_go_for_big_team_nogo_for_solo():
    g = GOOD_GATES.model_copy(update={"estimated_hours": 150})
    big = evaluate(dims([4, 4, 4, 4, 4, 4]), profile(hours=10, weeks=10, team=2), g, CFG)
    solo = evaluate(dims([4, 4, 4, 4, 4, 4]), profile(hours=2, weeks=10, team=1), g, CFG)
    assert big.verdict == Verdict.GO and solo.verdict == Verdict.NO_GO


def test_feasibility_gate_exact_hours_passes():
    g = GOOD_GATES.model_copy(update={"estimated_hours": 240})
    assert evaluate(dims(WORKED), profile(), g, CFG).gates["feasibility"] == "pass"


def test_risk_gate_names_blocker():
    g = GOOD_GATES.model_copy(update={"blockers": ["stores medical records without consent"]})
    r = evaluate(dims(WORKED), profile(), g, CFG)
    assert r.verdict == Verdict.NO_GO and "medical records" in r.gate_messages["risk"]


def test_duplicate_gate_names_product():
    v = list(WORKED); v[2] = 2.5
    g = GOOD_GATES.model_copy(update={"duplicate_of": "Notion"})
    r = evaluate(dims(v), profile(), g, CFG)
    assert r.verdict == Verdict.NO_GO and "Notion" in r.gate_messages["duplicate"]


def test_duplicate_gate_overridden_by_differentiation_3():
    g = GOOD_GATES.model_copy(update={"duplicate_of": "Notion"})
    r = evaluate(dims(WORKED), profile(), g, CFG)  # differentiation 3.0
    assert r.gates["duplicate"] == "pass"


def test_gate_order_evidence_before_feasibility():
    g = GateInputs(n_sources=0, n_platforms=0, estimated_hours=10_000)
    assert evaluate(dims(WORKED), profile(), g, CFG).verdict == Verdict.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------- thresholds
def score_for(target):
    """All six dims equal => weighted score = 20 * value."""
    return [target / 20] * 6


def test_exact_T_go_is_go():
    r = evaluate(dims(score_for(70)), profile(), GOOD_GATES, CFG)
    assert r.score == 70 and r.verdict == Verdict.GO


def test_just_below_T_go_is_pivot():
    r = evaluate(dims(score_for(69)), profile(), GOOD_GATES, CFG)
    assert r.verdict == Verdict.PIVOT and r.weakest_dimension is not None


def test_exact_T_no_is_pivot():
    assert evaluate(dims(score_for(50)), profile(), GOOD_GATES, CFG).verdict == Verdict.PIVOT


def test_below_T_no_is_nogo():
    assert evaluate(dims(score_for(49)), profile(), GOOD_GATES, CFG).verdict == Verdict.NO_GO


def test_floor_breach_turns_go_into_pivot():
    r = evaluate(dims([5, 1.0, 5, 5, 5, 5]), profile(), GOOD_GATES, CFG)
    assert r.score >= 70 and r.verdict == Verdict.PIVOT and r.weakest_dimension == "competition"


def test_floor_exact_value_is_not_a_breach():
    r = evaluate(dims([5, 1.5, 5, 5, 5, 5]), profile(), GOOD_GATES, CFG)
    assert r.verdict == Verdict.GO


def test_floor_ignores_learning():
    r = evaluate(dims([5, 5, 5, 5, 5, 0.5]), profile("startup"), GOOD_GATES, CFG)
    assert r.verdict == Verdict.GO


# ---------------------------------------------------------------- confidence
def test_confidence_formula():
    d = dims(WORKED, conf=0.6)
    assert overall_confidence(d, 5, CFG) == pytest.approx(0.7 * 0.6 + 0.3)
    assert overall_confidence(d, 3, CFG) == pytest.approx(0.7 * 0.6 + 0.3 * 0.6)


def test_low_confidence_abstains():
    r = evaluate(dims(WORKED, conf=0.2), profile(), GOOD_GATES.model_copy(update={"n_sources": 3}), CFG)
    assert r.verdict == Verdict.INSUFFICIENT_EVIDENCE and "confidence" in r.missing[0]


def test_confidence_exactly_0_5_is_enough():
    # 0.7*x + 0.3*1 = 0.5 -> x = 2/7
    r = evaluate(dims(score_for(80), conf=2 / 7), profile(), GOOD_GATES, CFG)
    assert r.verdict != Verdict.INSUFFICIENT_EVIDENCE


def test_abstained_scorer_gives_insufficient_evidence():
    d = dims(WORKED)
    d[0] = d[0].model_copy(update={"abstained": True, "evidence_ids": []})
    r = evaluate(d, profile(), GOOD_GATES, CFG)
    assert r.verdict == Verdict.INSUFFICIENT_EVIDENCE and "demand_pain" in r.missing[0]


# ---------------------------------------------------------------- sensitivity
def test_sensitivity_runs_14():
    r = evaluate(dims(WORKED), profile(), GOOD_GATES, CFG)
    assert r.sensitivity["runs"] == 14


def test_clear_go_is_stable():
    r = evaluate(dims([5, 5, 5, 5, 5, 5]), profile(), GOOD_GATES, CFG)
    assert r.verdict == Verdict.GO and r.stability == "STABLE" and r.sensitivity["flipped"] == 0


def test_least_confident_score_moved():
    conf = [0.9, 0.9, 0.9, 0.3, 0.9, 0.9]
    r = evaluate(dims(WORKED, conf=conf), profile(), GOOD_GATES, CFG)
    assert r.sensitivity["least_confident"] == "feasibility"


# ---------------------------------------------------------------- what-if
def test_whatif_sorted_smallest_first():
    r = evaluate(dims(score_for(66)), profile(), GOOD_GATES, CFG)
    deltas = [w.to_score - w.from_score for w in r.what_would_make_go]
    assert deltas == sorted(deltas)
    assert all(w.new_verdict == "GO" for w in r.what_would_make_go)


def test_whatif_for_feasibility_gate_suggests_scope_cut():
    g = GOOD_GATES.model_copy(update={"estimated_hours": 300})
    r = evaluate(dims(WORKED), profile(), g, CFG)
    assert "Cut scope by about 60 hours" in r.what_would_make_go[0].change


def test_whatif_empty_when_nothing_can_reach_go():
    r = evaluate(dims([0, 0, 0, 0, 0, 0]), profile(), GOOD_GATES, CFG)
    assert r.verdict == Verdict.NO_GO and r.what_would_make_go == []


# ---------------------------------------------------------------- challenge
def test_challenge_lowers_score_and_confidence():
    out = apply_challenge(dims(WORKED), {"competition": 1}, CFG)
    c = next(d for d in out if d.dimension == "competition")
    assert c.score == 1.5 and c.confidence == pytest.approx(0.7)


def test_challenge_capped_at_1():
    out = apply_challenge(dims(WORKED), {"demand_pain": 5}, CFG)
    d = next(d for d in out if d.dimension == "demand_pain")
    assert d.score == 2.5 and d.confidence == pytest.approx(0.6)


# ---------------------------------------------------------------- determinism
def test_same_input_same_output():
    a = evaluate(dims(WORKED), profile(), GOOD_GATES, copy.deepcopy(CFG))
    b = evaluate(dims(WORKED), profile(), GOOD_GATES, copy.deepcopy(CFG))
    assert a.model_dump() == b.model_dump()
