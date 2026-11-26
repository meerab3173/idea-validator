#!/usr/bin/env bash
# Minimal end-to-end check after a deploy: health of every service + one
# engine-only verdict through the cluster network.
set -euo pipefail
NS=idea-validator
kubectl -n $NS run smoke-$RANDOM --rm -i --restart=Never --image=curlimages/curl:8.10.1 -- sh -c '
set -e
for s in gateway profile orchestrator scouts tools kb analyst ideation validators scorer verdict critic agentops; do
  curl -fsS http://$s:8000/health >/dev/null && echo "ok $s"
done
curl -fsS -X POST http://verdict:8000/verdict -H "Content-Type: application/json" -d "{
 \"scores\":[
  {\"dimension\":\"demand_pain\",\"score\":3.5,\"confidence\":0.8,\"evidence_ids\":[\"a#c0\"]},
  {\"dimension\":\"competition\",\"score\":2.0,\"confidence\":0.8,\"evidence_ids\":[\"a#c0\"]},
  {\"dimension\":\"differentiation\",\"score\":3.0,\"confidence\":0.8,\"evidence_ids\":[\"a#c0\"]},
  {\"dimension\":\"feasibility\",\"score\":4.0,\"confidence\":0.8,\"evidence_ids\":[\"a#c0\"]},
  {\"dimension\":\"risk\",\"score\":3.5,\"confidence\":0.8,\"evidence_ids\":[\"a#c0\"]},
  {\"dimension\":\"learning\",\"score\":4.5,\"confidence\":0.8,\"evidence_ids\":[\"a#c0\"]}],
 \"profile\":{\"user_id\":\"smoke\",\"hours_per_week\":10,\"weeks_available\":12,\"team_size\":2,\"goal\":\"portfolio\"},
 \"gates\":{\"n_sources\":5,\"n_platforms\":3,\"estimated_hours\":100}}" | grep -q "\"score\":70.5" && echo "verdict engine OK (70.5)"
'
