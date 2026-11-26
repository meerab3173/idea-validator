"""M6i ingestion pipeline (CronJob):  scouts -> KB ingest (dedupe, chunk,
embed, index) -> niche analysis (M7) -> drift report (M13).

  python -m src.pipeline --sources hn github yc reddit --pages 10
  python -m src.pipeline --from-snapshot /app/snapshot/cards.jsonl   # offline restore
Repeatable: the KB dedupes by normalised URL and name+summary.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from common.config import SERVICE_URLS

from .main import make_fetch, save_and_ingest
from .sources import run_source

QUERIES = {  # several queries per source to reach 1,500+ cards
    "hn": ["", "students", "tool", "app", "saas", "open source", "ai", "education"],
    "github": ["topic:saas", "topic:productivity", "topic:education", "topic:developer-tools", "topic:fintech",
               "topic:health", "topic:ecommerce"],
    "yc": [None],
    "reddit": [None],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", default=["hn", "github", "yc"])
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--from-snapshot", default="")
    a = ap.parse_args()
    summary = {}
    if a.from_snapshot:
        cards = [json.loads(l) for l in Path(a.from_snapshot).read_text().splitlines() if l.strip()]
        by_src: dict[str, list] = {}
        for c in cards:
            by_src.setdefault(c["source"], []).append(c)
        for src, cs in by_src.items():
            for i in range(0, len(cs), 200):
                r = httpx.post(f"{SERVICE_URLS['kb']}/ingest", json={"source": src, "cards": cs[i:i + 200]}, timeout=900)
                summary.setdefault(src, []).append(r.json())
    else:
        for src in a.sources:
            for q in QUERIES[src]:
                kw = {"pages": a.pages}
                if q is not None:
                    kw["query"] = q
                res = run_source(src, make_fetch(f"ingest-{src}"), **kw)
                save_and_ingest(res)
                summary.setdefault(src, []).append({"query": q, "cards": len(res["cards"]),
                                                    "errors": len(res["errors"])})
    try:
        summary["analysis"] = httpx.post(f"{SERVICE_URLS['analyst']}/analyse", timeout=900).json()
        summary["drift"] = httpx.post(f"{SERVICE_URLS['agentops']}/drift", timeout=120).json().get("status")
    except httpx.HTTPError as e:
        summary["post_steps_error"] = repr(e)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
