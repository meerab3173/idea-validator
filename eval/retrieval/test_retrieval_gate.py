"""Retrieval quality gate (GitHub Actions). Fails if recall@5 or MRR drops
below the stored baseline. Runs offline on the snapshot with the in-memory
index; `scripts/eval_retrieval_live.py` runs the same queries against the
real KB service for the report."""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "libs" / "common")]
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kb_core", ROOT / "services/kb/src/core.py")
_kb = importlib.util.module_from_spec(_spec)
sys.modules["kb_core"] = _kb
_spec.loader.exec_module(_kb)
InMemoryIndex, mrr, recall_at_k = _kb.InMemoryIndex, _kb.mrr, _kb.recall_at_k
from common.embedding import hashing_embed  # noqa: E402

BASELINE = json.loads((Path(__file__).parent / "baseline.json").read_text())


def run(mode: str) -> dict:
    cards = [json.loads(l) for l in (ROOT / "data/snapshot/cards.sample.jsonl").read_text().splitlines()]
    idx = InMemoryIndex(embed=hashing_embed)
    idx.add_cards(cards)
    qs = yaml.safe_load((Path(__file__).parent / "queries.yaml").read_text())["queries"]
    r5, m = [], []
    for q in qs:
        res = [x["card_id"] for x in idx.search(q["q"], k=5, mode=mode)]
        r5.append(recall_at_k(res, set(q["relevant"]), 5))
        m.append(mrr(res, set(q["relevant"])))
    return {"recall@5": sum(r5) / len(r5), "mrr": sum(m) / len(m), "n": len(qs)}


def test_at_least_20_queries():
    assert run("hybrid")["n"] >= 20


def test_hybrid_not_below_baseline():
    r = run("hybrid")
    print(r)
    assert r["recall@5"] >= BASELINE["recall@5"] - 1e-9
    assert r["mrr"] >= BASELINE["mrr"] - 1e-9


if __name__ == "__main__":
    for mode in ("keyword", "vector", "hybrid"):
        print(mode, run(mode))
