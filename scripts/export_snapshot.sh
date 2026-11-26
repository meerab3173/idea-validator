#!/usr/bin/env bash
# Save a snapshot of all cards so the system does not depend on websites being up.
set -euo pipefail
NS=idea-validator
cd "$(dirname "$0")/.."
kubectl -n $NS exec deploy/kb -- python -c "
import json,urllib.request as u
for c in json.load(u.urlopen('http://localhost:8000/cards')): print(json.dumps(c))" > data/snapshot/cards.jsonl
wc -l data/snapshot/cards.jsonl
