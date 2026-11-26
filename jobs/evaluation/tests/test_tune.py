import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metrics import confusion  # noqa: E402
import tune  # noqa: E402

DIMS = ["demand_pain", "competition", "differentiation", "feasibility", "risk", "learning"]
PROF = {"p": {"user_id": "x", "hours_per_week": 10, "weeks_available": 12, "team_size": 2, "goal": "portfolio"}}
GATES = {"n_sources": 5, "n_platforms": 3, "estimated_hours": 100}


def row(human, v):
    return {"human": human, "profile": "p", "gate_inputs": GATES,
            "scores": [{"dimension": d, "score": v, "confidence": 0.8, "evidence_ids": ["a#c0"]} for d in DIMS]}


def test_confusion_counts_false_go():
    c = confusion([("NO-GO", "GO"), ("GO", "GO")])
    assert c["false_go"] == 1 and c["agreement"] == 0.5


def test_tuning_improves_agreement():
    # humans call 3.3 (score 66) a GO; default T_go=70 calls it PIVOT
    rows = [row("GO", 3.3), row("GO", 3.4), row("NO-GO", 2.0), row("PIVOT", 2.8)]
    import yaml
    cfg = yaml.safe_load(open(Path(tune.ROOT) / "config/verdict.yaml"))
    before, after, th = tune.tune(rows, PROF, cfg)
    assert after["agreement"] > before["agreement"] and th["T_go"] <= 66 and after["false_go"] == 0
