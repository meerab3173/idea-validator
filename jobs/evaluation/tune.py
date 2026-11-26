"""Tune T_go, T_no and floor OFFLINE (Guide Section 10).
Reads an eval result (which stores each idea's six scores and gate inputs),
re-runs the deterministic Verdict Engine for every candidate setting and
picks the one with the best agreement, penalising false GOs 3x.

  python jobs/evaluation/tune.py eval/results/latest.json
Prints before/after confusion matrices for the report. Then copy the chosen
values into config/verdict.yaml, bump `version`, run scripts/make_configmaps.py.
"""
from __future__ import annotations

import copy
import itertools
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "libs/common")]
import importlib.util  # noqa: E402

from common.schemas import DimensionScore, GateInputs, StudentProfile  # noqa: E402

_spec = importlib.util.spec_from_file_location("verdict_engine", ROOT / "services/verdict/src/engine.py")
_engine = importlib.util.module_from_spec(_spec)
sys.modules["verdict_engine"] = _engine
_spec.loader.exec_module(_engine)
evaluate = _engine.evaluate

sys.path.insert(0, str(Path(__file__).parent))
from metrics import LABELS, confusion  # noqa: E402


def predict(rows, profiles, cfg):
    pairs = []
    for r in rows:
        if not r.get("scores"):
            continue
        res = evaluate([DimensionScore(**s) for s in r["scores"]], StudentProfile(**profiles[r["profile"]]),
                       GateInputs(**(r.get("gate_inputs") or {})), cfg)
        pairs.append((r["human"], res.verdict.value))
    return pairs


def objective(c):
    return c["agreement"] - 3 * c["false_go"] / max(1, c["n"])


def tune(rows, profiles, cfg):
    before = confusion(predict(rows, profiles, cfg))
    best, best_cfg = before, cfg
    for t_go, t_no, floor in itertools.product(range(60, 81, 2), range(40, 61, 2), (1.0, 1.5, 2.0)):
        if t_no >= t_go:
            continue
        c2 = copy.deepcopy(cfg)
        c2["thresholds"] = {"T_go": t_go, "T_no": t_no, "floor": floor}
        m = confusion(predict(rows, profiles, c2))
        # prefer better objective; on ties prefer values closer to the defaults (less overfit)
        dist = abs(t_go - 70) + abs(t_no - 50)
        if (objective(m), -dist) > (objective(best), -(abs(best_cfg["thresholds"]["T_go"] - 70) + abs(best_cfg["thresholds"]["T_no"] - 50))):
            best, best_cfg = m, c2
    return before, best, best_cfg["thresholds"]


def show(name, c):
    print(f"\n{name}: agreement {c['agreement']}, false GO {c['false_go']}, n {c['n']}")
    print("human \\ system".ljust(24) + "".join(l[:6].ljust(8) for l in LABELS))
    for h in LABELS:
        print(h.ljust(24) + "".join(str(c["matrix"][h][p]).ljust(8) for p in LABELS))


if __name__ == "__main__":
    res = json.loads(Path(sys.argv[1]).read_text())
    labelled = yaml.safe_load((ROOT / "eval/labelled/ideas.yaml").read_text())
    cfg = yaml.safe_load((ROOT / "config/verdict.yaml").read_text())
    before, after, th = tune(res["rows"], labelled["profiles"], cfg)
    show("BEFORE", before); show("AFTER", after)
    print("\nchosen thresholds:", th)
