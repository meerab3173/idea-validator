#!/usr/bin/env bash
# NetworkPolicy test (screenshot this): a non-M5 pod cannot reach the internet,
# the tool layer (M5) can. Requires a CNI that enforces policies (Calico/Cilium).
NS=idea-validator
echo "--- from verdict (should FAIL / time out)"
kubectl -n $NS exec deploy/verdict -- python -c "import urllib.request as u; print(u.urlopen('https://api.github.com', timeout=5).status)" \
  && echo "UNEXPECTED: verdict reached the internet" || echo "BLOCKED as expected"
echo "--- from tools (should print 200)"
kubectl -n $NS exec deploy/tools -- python -c "import urllib.request as u; print(u.urlopen('https://api.github.com', timeout=5).status)"
