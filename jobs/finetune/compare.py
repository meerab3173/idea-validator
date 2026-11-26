"""Step 6 — compare base, fine-tuned and hosted models on the hand-checked test
set (Guide 6.3): MAE vs human, share within 1 point, valid-JSON rate, share of
real evidence ids, latency and cost per score. Writes a markdown table.

  # start the base and fine-tuned models in Ollama locally first:
  #   ollama pull llama3.2:1b ; ollama create scorer-lora -f services/model-server/Modelfile
  python jobs/finetune/compare.py --base llama3.2:1b --ft scorer-lora --hosted llama-3.1-8b-instant
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "libs/common")]
from common.llm import parse_json  # noqa: E402


def score_row(pred_text: str, human: dict, allowed: list[str]) -> dict:
    out = {"valid": False, "abs_err": None, "real_ids": None}
    try:
        p = parse_json(pred_text)
    except Exception:
        return out
    if human.get("abstain"):
        out.update(valid=True, abs_err=0.0 if p.get("abstain") else None, real_ids=1.0)
        return out
    if "score" not in p or not isinstance(p.get("evidence_ids"), list):
        return out
    ids = p["evidence_ids"]
    out.update(valid=True, abs_err=abs(float(p["score"]) - float(human["score"])),
               real_ids=(sum(i in allowed for i in ids) / len(ids)) if ids else 0.0)
    return out


def summarise(rows: list[dict], latencies: list[float], cost: float) -> dict:
    errs = [r["abs_err"] for r in rows if r["abs_err"] is not None]
    n = len(rows)
    return {"n": n, "mae": round(sum(errs) / len(errs), 3) if errs else None,
            "within_1": round(sum(e <= 1 for e in errs) / n, 3) if n else 0,
            "valid_json": round(sum(r["valid"] for r in rows) / n, 3) if n else 0,
            "real_evidence_ids": round(sum(r["real_ids"] or 0 for r in rows) / n, 3) if n else 0,
            "latency_ms": round(1000 * sum(latencies) / len(latencies)) if latencies else None,
            "cost_per_score_usd": round(cost / n, 6) if n else 0}


def run_model(name: str, base_url: str, api_key: str, test: list[dict], price=(0.0, 0.0)) -> dict:
    import httpx
    rows, lat, cost = [], [], 0.0
    for ex in test:
        msgs = ex["messages"][:2]
        t0 = time.time()
        try:
            r = httpx.post(f"{base_url}/chat/completions", timeout=120, headers={"Authorization": f"Bearer {api_key}"},
                           json={"model": name, "messages": msgs, "temperature": 0, "max_tokens": 250})
            d = r.json()
            text = d["choices"][0]["message"]["content"]
            u = d.get("usage", {})
            cost += u.get("prompt_tokens", 0) / 1000 * price[0] + u.get("completion_tokens", 0) / 1000 * price[1]
        except Exception as e:  # noqa: BLE001
            text = f"ERROR {e}"
        lat.append(time.time() - t0)
        rows.append(score_row(text, json.loads(ex["messages"][2]["content"]), ex["meta"]["allowed_ids"]))
    return summarise(rows, lat, cost)


if __name__ == "__main__":
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--ft", required=True); ap.add_argument("--hosted", required=True)
    ap.add_argument("--local-url", default="http://localhost:11434/v1")
    a = ap.parse_args()
    test = [json.loads(l) for l in (ROOT / "data/finetune/test.jsonl").read_text().splitlines()]
    test = [t for t in test if t["meta"]["checked"]]
    res = {
        "base": run_model(a.base, a.local_url, "ollama", test),
        "fine-tuned": run_model(a.ft, a.local_url, "ollama", test),
        "hosted": run_model(a.hosted, os.environ.get("LLM_UPSTREAM", "https://api.groq.com/openai/v1"),
                            os.environ.get("LLM_UPSTREAM_KEY", ""), test, price=(0.00005, 0.00008)),
    }
    cols = ["n", "mae", "within_1", "valid_json", "real_evidence_ids", "latency_ms", "cost_per_score_usd"]
    md = "| model | " + " | ".join(cols) + " |\n|" + "---|" * (len(cols) + 1) + "\n"
    md += "\n".join(f"| {m} | " + " | ".join(str(v[c]) for c in cols) + " |" for m, v in res.items())
    out = ROOT / "eval/results/finetune_comparison.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md + "\n")
    print(md)
