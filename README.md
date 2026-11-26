# Idea Generator with Go / No-Go

This is the CS4032 semester project. It is a multi-agent system that suggests project ideas for a student (**Discover**) and gives a verdict on an idea (**Validate**): GO, PIVOT, NO-GO or INSUFFICIENT EVIDENCE. Each verdict comes with its evidence, what would change it, and how stable it is. The whole system runs on Kubernetes, with one container per module.

> **Principle:** models only produce evidence-backed scores. The verdict always comes from `services/verdict` (M11), which is plain, unit-tested code.

## Module → folder map

| Module | Folder | Image |
|---|---|---|
| M1 Web UI + API gateway | `services/ui` (React), `services/gateway` (FastAPI) | `ui`, `gateway` |
| M2 Profile, session, cache | `services/profile` (routes → services → repositories, SQL migrations, Redis) | `profile` |
| M3 Orchestrator | `services/orchestrator` (Validate/Discover state machines, budgets, record/replay) | `orchestrator` |
| M4 Scouts | `services/scouts` (HN, GitHub, YC, Reddit, via M5 only) + CronJobs | `scouts` |
| M5 Tool layer | `services/tools` (allow-list, robots.txt, rate limits, cache, sanitiser, LLM egress) | `tools` |
| M6 Knowledge base | `services/kb` (Postgres + pgvector, hybrid search + rerank) | `kb` |
| M6i Ingestion | `services/scouts/src/pipeline.py` (CronJob `ingestion`) | `scouts` |
| M7 Niche & trend analyst | `services/analyst` | `analyst` |
| M8 Idea generator | `services/ideation` (Ideator, Gap Analyst, Skeptic debate, ≤ 3 rounds) | `ideation` |
| M9 Validation agents | `services/validators` (4 parallel scorers + computed features + gate inputs) | `validators` |
| M10 Scoring model | `services/scorer` (validate / retry / fallback) + `services/model-server` (Ollama, GGUF) | `scorer`, `model-server` |
| M10t Fine-tuning | `jobs/finetune` | – |
| M11 Verdict engine | `services/verdict` (+ `config/verdict.yaml` as a ConfigMap) | `verdict` |
| M12 Critic & guardrails | `services/critic` | `critic` |
| M13 AgenticOps | `services/agentops` (traces, dashboard, drift, records) + `jobs/evaluation` | `agentops`, `evaluation` |
| M14 Platform | `.github/workflows`, `Jenkinsfile`, `k8s/`, `scripts/` | – |

Shared code lives in `libs/common/common`: schemas (Guide §2), config, tracing, the LLM client with record/replay, and prompts.

## Run the tests (no Docker needed)

```bash
pip install -r requirements-dev.txt
./scripts/run_tests.sh               # 119 Python tests
cd services/ui && npm install && npm test
```

## Run locally with Docker Compose (development)

```bash
cp .env.example .env                 # set POSTGRES_PASSWORD, JWT_SECRET, LLM_UPSTREAM_KEY
docker compose up --build
# load the card snapshot once:
docker compose exec scouts python -m src.pipeline --from-snapshot /app/snapshot/cards.sample.jsonl
# UI: http://localhost:3000   API: http://localhost:8080   Dashboard: http://localhost:8090/dashboard
```

## Deploy on Kubernetes (minikube with Calico, so NetworkPolicy is enforced)

```bash
minikube start --cni=calico --cpus=4 --memory=8192
minikube addons enable ingress && minikube addons enable metrics-server
eval $(minikube docker-env)                      # build straight into minikube's Docker
./scripts/build_images.sh dev
kubectl apply -f k8s/00-namespace.yaml
kubectl -n idea-validator create secret generic app-secrets \
  --from-literal=POSTGRES_PASSWORD=... --from-literal=JWT_SECRET=... \
  --from-literal=LLM_UPSTREAM_KEY=... --from-literal=GITHUB_TOKEN=... --from-literal=EVAL_PASSWORD=...
kubectl apply -k k8s/
kubectl -n idea-validator get pods -w
echo "$(minikube ip) ideas.local" | sudo tee -a /etc/hosts   # then open http://ideas.local
```

Useful scripts:

- `scripts/smoke_test.sh`: health of every service, plus the brief's worked example (expects 70.5).
- `scripts/netpol_test.sh`: shows that only M5 can reach the internet.
- `scripts/measure_resources.sh`: `kubectl top` samples, used to set requests and limits.
- `scripts/replay.py <run_id>`: replays a stored run from its recorded tool results.
- `kubectl create -f k8s/eval-job.yaml`: runs the evaluation harness.
- `python jobs/evaluation/tune.py eval/results/latest.json`: threshold tuning, with before/after confusion matrices.

## Change the rules

1. Edit `config/verdict.yaml` (weights, thresholds, floor) or a rubric in `rubrics/`, then bump its `version` (and `set` in `rubrics/REGISTRY.yaml`).
2. Run `python scripts/make_configmaps.py`. CI fails if you forget.
3. Re-run the evaluation. Cache keys include the profile, rubric and weights versions, so old verdicts are never served after a change.

## Data and ethics

Data comes only from official APIs and open datasets. The project respects robots.txt and sends a clear User-Agent. Each source has its own rate limit. No logins and no private data are used. Every card keeps its source URL, and verdict cards link to it. Fetched text is treated as data: the sanitiser in M5 strips instructions aimed at models, and every prompt tells the model never to follow instructions found in evidence. `data/snapshot/` keeps a copy of the cards, so the system does not depend on websites being up.
