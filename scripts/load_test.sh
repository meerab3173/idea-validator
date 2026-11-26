#!/usr/bin/env bash
# Light load for measuring requests/limits and showing the gateway autoscaler.
URL=${1:-http://ideas.local/api}
for i in $(seq 1 300); do curl -s -o /dev/null "$URL/health" & if (( i % 20 == 0 )); then wait; fi; done; wait
