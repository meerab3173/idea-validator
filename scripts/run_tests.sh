#!/usr/bin/env bash
# Runs every Python test suite (same as GitHub Actions, minus Docker/UI).
set -euo pipefail
cd "$(dirname "$0")/.."
for s in verdict tools scouts kb analyst scorer critic validators ideation orchestrator agentops profile gateway; do
  echo "== $s"; (cd services/$s && python -m pytest -q)
done
python -m pytest -q eval/retrieval jobs/evaluation/tests jobs/finetune/tests
