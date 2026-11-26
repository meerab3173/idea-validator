#!/usr/bin/env bash
set -euo pipefail
TAG=${1:?tag}; REGISTRY=${REGISTRY:?set REGISTRY}
for s in gateway profile orchestrator scouts tools kb analyst ideation validators scorer verdict critic agentops ui evaluation model-server; do
  docker image inspect $REGISTRY/$s:$TAG >/dev/null 2>&1 && docker push $REGISTRY/$s:$TAG
done
