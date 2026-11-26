"""Step 3 — split BY IDEA (never by row) into train/test, chat-format JSONL.
Hand-checked examples go to the test set (used for evaluation, Guide 6.1).

  python jobs/finetune/split.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def to_chat(r: dict) -> dict:
    return {"messages": [{"role": "system", "content": r["system"]},
                         {"role": "user", "content": r["user"]},
                         {"role": "assistant", "content": json.dumps(r["label"])}],
            "meta": {"idea_id": r["idea_id"], "dimension": r["dimension"], "checked": r["checked"],
                     "allowed_ids": r["allowed_ids"]}}


def split(rows: list[dict], test_frac: float = 0.2, seed: int = 42) -> tuple[list[dict], list[dict]]:
    ideas = sorted({r["idea_id"] for r in rows})
    checked_ideas = sorted({r["idea_id"] for r in rows if r["checked"]})
    rng = random.Random(seed)
    test_ideas = set(checked_ideas)
    others = [i for i in ideas if i not in test_ideas]
    rng.shuffle(others)
    while len(test_ideas) < round(len(ideas) * test_frac) and others:
        test_ideas.add(others.pop())
    train = [r for r in rows if r["idea_id"] not in test_ideas]
    test = [r for r in rows if r["idea_id"] in test_ideas]
    return train, test


if __name__ == "__main__":
    rows = [json.loads(l) for l in (ROOT / "data/finetune/drafts.jsonl").read_text().splitlines()]
    train, test = split(rows)
    for name, part in (("train", train), ("test", test)):
        (ROOT / f"data/finetune/{name}.jsonl").write_text("\n".join(json.dumps(to_chat(r)) for r in part) + "\n")
    print(f"train {len(train)} rows / test {len(test)} rows "
          f"(checked in test: {sum(r['checked'] for r in test)})")
