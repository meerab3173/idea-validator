# Report outline (PDF, at most 10 pages, not counting screenshots)

1. **Summary and changes from the given architecture.** Mention the extras: M2 is a separate profile service, hosted-LLM egress goes through M5 (DDR-003), and M8 has `/skeptic` and `/concretize`.
2. **Modules and architecture figure.** Redraw Figure 1 with your actual services and ports.
3. **Verdict design.** Gates, weights (justify any change), thresholds, rubrics (`rubrics/*.yaml`), tuning results with BEFORE/AFTER confusion matrices (`jobs/evaluation/tune.py` prints both), false GOs reported separately, and one worked example.
4. **Knowledge base.** Sources, card counts per source (`GET kb/stats`), freshness, and retrieval results for keyword vs vector vs hybrid on 20+ queries.
5. **Fine-tuning.** Data (count, hand-checked count, split by idea), settings (`jobs/finetune/config.yaml`), the comparison table (`eval/results/finetune_comparison.md`), and one case where it did not help.
6. **AgenticOps.** Trace example, dashboard, drift report, budgets, behaviour tests, and replay.
7. **Platform.** GitHub Actions and Jenkins pipelines, Kubernetes design (objects table), the NetworkPolicy test, and how requests/limits were measured (`scripts/measure_resources.sh` output).
8. **Known limits and next steps.**

## Screenshot checklist (one-line caption each)
- [ ] protected main + PR with required checks
- [ ] the merge-conflict PR
- [ ] green and failing GitHub Actions run
- [ ] green and failing Jenkins run
- [ ] `kubectl get pods` all Running
- [ ] a rollout and a rollback
- [ ] NetworkPolicy test (verdict blocked, tools OK)
- [ ] UI: profile, Discover results, verdict card, challenge, what-if version 2, INSUFFICIENT EVIDENCE
- [ ] a trace, the dashboard, a drift report
- [ ] retrieval result table, fine-tuning comparison table
