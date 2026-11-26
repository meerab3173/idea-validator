"""Step 2 — hand-check drafts (at least 60). Shows each example, lets you keep
or fix the score/evidence, and marks it checked=True with your initials.

  python jobs/finetune/review.py --who MR --limit 30
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data/finetune/drafts.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", required=True)
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    rows = [json.loads(l) for l in P.read_text().splitlines()]
    n = 0
    for r in rows:
        if r["checked"] or n >= a.limit:
            continue
        print("\n" + "=" * 80 + f"\n[{r['dimension']}]\n{r['user']}\n\nDRAFT: {json.dumps(r['label'])}")
        ans = input("Enter=keep | new score (e.g. 2.5) | a=abstain | s=skip > ").strip()
        if ans == "s":
            continue
        if ans == "a":
            r["label"] = {"abstain": True}
        elif ans:
            r["label"]["score"] = float(ans)
            ids = input(f"evidence ids (comma) [{','.join(r['label'].get('evidence_ids', []))}] > ").strip()
            if ids:
                r["label"]["evidence_ids"] = [i.strip() for i in ids.split(",")]
            reason = input("reason (Enter keeps) > ").strip()
            if reason:
                r["label"]["reason"] = reason
        r["checked"], r["checked_by"] = True, a.who
        n += 1
    P.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"checked {n}; total checked {sum(r['checked'] for r in rows)}")


if __name__ == "__main__":
    main()
