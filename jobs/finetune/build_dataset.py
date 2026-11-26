"""Step 1 — build >= 300 (idea, evidence, dimension) examples and draft labels
with a hosted model using the SAME rubric prompt the scorer serves with.

  python jobs/finetune/build_dataset.py --cards data/snapshot/cards.jsonl --n 360
Writes data/finetune/drafts.jsonl. Needs LLM_BASE_URL/LLM_API_KEY/LLM_MODEL
for a hosted model (run on your laptop, outside the cluster).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "libs/common"), str(ROOT / "services/kb")]  # run as a script, so `src` = kb
from common.embedding import hashing_embed  # noqa: E402
from common.llm import LLM, parse_json  # noqa: E402
from common.prompts import scorer_system, scorer_user  # noqa: E402
from common.schemas import DIMENSIONS  # noqa: E402
from src.core import InMemoryIndex  # noqa: E402

PROFILES = [  # varied students so feasibility/learning labels cover all levels
    {"skills": ["react", "sql"], "hours_per_week": 10, "weeks_available": 12, "team_size": 2, "compute": "laptop", "goal": "portfolio", "interests": ["devops"]},
    {"skills": ["python"], "hours_per_week": 3, "weeks_available": 8, "team_size": 1, "compute": "laptop", "goal": "course_project", "interests": []},
    {"skills": ["react", "python", "flutter", "ml"], "hours_per_week": 20, "weeks_available": 16, "team_size": 3, "compute": "free_gpu", "goal": "startup", "interests": ["ml"]},
]


def labelled_texts() -> set[str]:
    d = yaml.safe_load((ROOT / "eval/labelled/ideas.yaml").read_text())
    return {i["idea"].lower() for i in d["ideas"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", default=str(ROOT / "data/snapshot/cards.jsonl"))
    ap.add_argument("--n", type=int, default=360)
    ap.add_argument("--out", default=str(ROOT / "data/finetune/drafts.jsonl"))
    a = ap.parse_args()
    rng = random.Random(42)
    cards = [json.loads(l) for l in Path(a.cards).read_text().splitlines() if l.strip()]
    banned = labelled_texts()
    idx = InMemoryIndex(embed=hashing_embed)
    idx.add_cards(cards)
    llm = LLM()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    with out.open("a") as f:
        for card in rng.sample(cards, min(len(cards), a.n // len(DIMENSIONS) + 20)):
            idea = f"{card['name']}: {card.get('summary') or card.get('text', '')[:200]}"
            if idea.lower() in banned:
                continue  # never train on the labelled (tuning) set
            # evidence = other cards; sometimes thin on purpose so low scores / abstains appear
            k = rng.choice([1, 3, 6, 8])
            ev = [e for e in idx.search(idea, k=k + 1) if e["card_id"] != card["id"]][:k]
            ev = [{"evidence_id": e["evidence_id"], "source": e["source"], "quote": e["quote"]} for e in ev]
            prof = rng.choice(PROFILES)
            for dim in DIMENSIONS:
                sys_p, user_p = scorer_system(dim), scorer_user(idea, prof, ev, None)
                try:
                    r = llm.complete(sys_p, user_p, max_tokens=250)
                    label = parse_json(r.text)
                except Exception as e:  # noqa: BLE001
                    print("skip", e)
                    continue
                f.write(json.dumps({"idea_id": card["id"], "dimension": dim, "system": sys_p, "user": user_p,
                                    "label": label, "allowed_ids": [e["evidence_id"] for e in ev],
                                    "checked": False}) + "\n")
                done += 1
            if done >= a.n:
                break
    print(f"wrote {done} drafts to {out}")


if __name__ == "__main__":
    main()
