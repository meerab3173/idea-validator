#!/usr/bin/env bash
# Deploy a tag to the cluster with a rolling update; undo automatically if a
# rollout does not become ready. Requires kubectl + kustomize (kubectl -k).
set -euo pipefail
TAG=${1:?tag}; REGISTRY=${REGISTRY:-idea-validator}; NS=idea-validator
cd "$(dirname "$0")/.."
python3 scripts/make_configmaps.py
cd k8s
for s in gateway ui profile orchestrator scouts tools kb analyst ideation validators scorer verdict critic agentops evaluation model-server; do
  if [ "$s" = model-server ] && ! docker image inspect $REGISTRY/model-server:$TAG >/dev/null 2>&1; then continue; fi
  kustomize edit set image idea-validator/$s=$REGISTRY/$s:$TAG
done
cd ..
kubectl apply -k k8s/
for d in $(kubectl -n $NS get deploy -o name); do
  if ! kubectl -n $NS rollout status $d --timeout=180s; then
    echo "rollout of $d failed -> undo"; kubectl -n $NS rollout undo $d; exit 1
  fi
done
git checkout -- k8s/kustomization.yaml 2>/dev/null || true
