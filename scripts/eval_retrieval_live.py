"""Retrieval quality on the REAL knowledge base (for the report and DDR-002).
Write eval/retrieval/queries.real.yaml first: 20+ queries, each with the card
ids a human judged relevant (find them with GET kb/cards or a keyword search).

  kubectl -n idea-validator port-forward svc/kb 8001:8000 &
  python scripts/eval_retrieval_live.py --kb http://localhost:8001
"""
import argparse
import json
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def search(kb, q, mode, k=5):
    req = urllib.request.Request(f"{kb}/search", data=json.dumps({"query": q, "k": k, "mode": mode}).encode(),
                                 headers={"Content-Type": "application/json"})
    return [r["card_id"] for r in json.load(urllib.request.urlopen(req))["results"]]


ap = argparse.ArgumentParser()
ap.add_argument("--kb", default="http://localhost:8001")
ap.add_argument("--queries", default=str(ROOT / "eval/retrieval/queries.real.yaml"))
a = ap.parse_args()
qs = yaml.safe_load(open(a.queries))["queries"]
rows = []
for mode in ("keyword", "vector", "hybrid"):
    r5 = mrr = 0.0
    for q in qs:
        res, rel = search(a.kb, q["q"], mode), set(q["relevant"])
        r5 += len(set(res) & rel) / len(rel)
        mrr += next((1 / (i + 1) for i, x in enumerate(res) if x in rel), 0)
    rows.append((mode, round(r5 / len(qs), 3), round(mrr / len(qs), 3)))
md = "| mode | recall@5 | MRR |\n|---|---|---|\n" + "\n".join(f"| {m} | {r} | {k} |" for m, r, k in rows)
(ROOT / "eval/results").mkdir(parents=True, exist_ok=True)
(ROOT / "eval/results/retrieval.md").write_text(md + f"\n\n{len(qs)} queries\n")
print(md)
