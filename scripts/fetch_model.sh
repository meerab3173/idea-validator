#!/usr/bin/env bash
# Download the fine-tuned GGUF from the GitHub release (outside the cluster) before building model-server.
set -euo pipefail
mkdir -p models
gh release download ${1:-model-v1} --pattern 'scorer-q4_k_m.gguf' --dir models --clobber
ls -lh models
