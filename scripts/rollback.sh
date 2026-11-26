#!/usr/bin/env bash
# Roll every deployment back to its previous ReplicaSet.
set -euo pipefail
NS=idea-validator
for d in $(kubectl -n $NS get deploy -o name); do kubectl -n $NS rollout undo $d || true; done
kubectl -n $NS get pods
