#!/usr/bin/env bash
# Measure real usage to set requests/limits (needs: minikube addons enable metrics-server).
# Run while scripts/load_test.sh is generating traffic; record peaks in docs/report.
NS=idea-validator
for i in $(seq 1 10); do date +%T; kubectl -n $NS top pods --no-headers; sleep 30; done | tee docs/resource-measurements.txt
echo "Rule used: request ~ p50 usage, limit ~ 2x observed peak (memory) / 3-5x (cpu)."
