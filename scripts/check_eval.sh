#!/usr/bin/env bash
# Nightly: run the evaluation Job in the cluster, copy results, compare with baseline.
set -euo pipefail
NS=idea-validator
cd "$(dirname "$0")/.."
JOB=$(kubectl -n $NS create -f k8s/eval-job.yaml -o name)
kubectl -n $NS wait --for=condition=complete $JOB --timeout=60m
POD=$(kubectl -n $NS get pods -l job-name=${JOB#job.batch/} -o name | head -1)
kubectl -n $NS logs $POD | tail -20
AG=$(kubectl -n $NS get pod -l app=agentops -o name | head -1)
mkdir -p eval/results
kubectl -n $NS exec ${AG} -- cat /data/eval-results/latest.json > eval/results/latest.json
python3 jobs/evaluation/check_eval.py eval/results/latest.json
