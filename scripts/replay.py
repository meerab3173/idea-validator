"""Replay a stored run with its recorded tool/model results (no network, no
model) and check the deterministic part gives the same verdict.

  kubectl -n idea-validator port-forward svc/agentops 8090:8000 &
  python scripts/replay.py run_ab12cd34 --agentops http://localhost:8090
"""
import argparse
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs/common"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m


E = load("verdict_engine", ROOT / "services/verdict/src/engine.py")
M = load("orch_machine", ROOT / "services/orchestrator/src/machine.py")
from common.schemas import DimensionScore, GateInputs, StudentProfile  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run_id"); ap.add_argument("--agentops", default="http://localhost:8090")
a = ap.parse_args()
rec = json.load(urllib.request.urlopen(f"{a.agentops}/records/{a.run_id}"))
vcfg = yaml.safe_load(open(ROOT / "config/verdict.yaml"))
bcfg = yaml.safe_load(open(ROOT / "config/budgets.yaml"))


def ev(p, accepted=None):
    dims = [DimensionScore(**s) for s in p["scores"]]
    if accepted:
        dims = E.apply_challenge(dims, accepted, vcfg)
    return E.evaluate(dims, StudentProfile(**p["profile"]), GateInputs(**p["gates"]), vcfg,
                      p["idea_id"], p["version"], p["run_id"]).model_dump(mode="json")


rp = M.ReplayClients(rec["tape"], ev, lambda p: ev(p, p["accepted"]))
vm = M.ValidateMachine(rp, bcfg, {})
r = vm.new(rec["idea"], rec["profile"], run_id=a.run_id + "-replay")
r.answers = {"replay": "yes"}
r = vm.run(r)
print("replayed state:", r.state.value, "| verdict:", r.verdict.get("verdict"), "| score:", r.verdict.get("score"))
for e in r.events:
    print("  ", e.get("type"), e.get("to") or e.get("agent") or "", e.get("verdict") or "")
