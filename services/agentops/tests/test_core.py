from src.core import distribution, drift_report, psi, summarise


def test_summarise():
    traces = [
        {"run_id": "run_1", "agent": "kb", "tool": "search_kb", "kind": "tool_call", "cost_usd": 0, "latency_ms": 50, "cache_hit": True},
        {"run_id": "run_1", "agent": "competition_scorer", "kind": "llm_call", "cost_usd": 0.002, "latency_ms": 900},
        {"run_id": "run_1", "agent": "tool_layer", "tool": "fetch", "kind": "tool_call", "output": "200 10B flagged=2", "latency_ms": 300},
    ]
    s = summarise(traces, [{"run_id": "run_1", "verdict": "GO"}])
    assert s["cost_per_verdict_usd"] == 0.002 and s["blocked_injections"] == 1
    assert s["cache_hit_rate"] == round(1 / 3, 3) and s["verdict_distribution"] == {"GO": 1}


def test_psi_zero_for_same_distribution():
    d = distribution(["GO", "NO-GO", "PIVOT"])
    assert psi(d, d) == 0


def test_drift_detects_shift_and_stale():
    r = drift_report({"cards_per_source": {}}, {"hn": 2, "github": 30},
                     ["GO"] * 10 + ["NO-GO"] * 10, ["NO-GO"] * 18 + ["GO"] * 2)
    assert r["status"] != "stable" and r["stale_sources"] == ["github"]
