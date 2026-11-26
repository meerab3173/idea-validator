#!/usr/bin/env bash
# Build one image per module, tagged by commit SHA (never only `latest`).
# On minikube without a registry: eval $(minikube docker-env) first, then images are already in the cluster.
set -euo pipefail
TAG=${1:?usage: build_images.sh <tag>}
cd "$(dirname "$0")/.."
REGISTRY=${REGISTRY:-idea-validator}
for s in gateway profile orchestrator scouts tools kb analyst ideation validators scorer verdict critic agentops; do
  docker build -f services/$s/Dockerfile -t $REGISTRY/$s:$TAG .
done
docker build -t $REGISTRY/ui:$TAG services/ui
docker build -f jobs/evaluation/Dockerfile -t $REGISTRY/evaluation:$TAG .
if [ -f models/scorer-q4_k_m.gguf ]; then
  docker build -f services/model-server/Dockerfile -t $REGISTRY/model-server:$TAG .
fi
