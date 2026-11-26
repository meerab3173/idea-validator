"""Nightly gate (Jenkins): compare latest eval with the stored baseline.
Fails if agreement drops more than 5 points or false-GO count rises."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
latest = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else root / "eval/results/latest.json").read_text())
base = json.loads((root / "eval/baseline.json").read_text())
ok = latest["agreement"] >= base["agreement"] - 0.05 and latest["false_go"] <= base["false_go"]
print(f"agreement {latest['agreement']} (baseline {base['agreement']}), false GO {latest['false_go']} "
      f"(baseline {base['false_go']}) -> {'OK' if ok else 'REGRESSION'}")
sys.exit(0 if ok else 1)
