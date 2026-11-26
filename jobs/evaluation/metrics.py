"""Verdict-agreement metrics shared by the harness and the tuner."""
LABELS = ["GO", "PIVOT", "NO-GO", "INSUFFICIENT_EVIDENCE"]


def confusion(pairs: list[tuple[str, str]]) -> dict:
    """pairs = [(human, system)]. false_go = system GO where humans said NO-GO
    (the worst error, reported separately)."""
    m = {h: {p: 0 for p in LABELS} for h in LABELS}
    for human, pred in pairs:
        m[human][pred] += 1
    n = len(pairs)
    agree = sum(m[l][l] for l in LABELS)
    return {"matrix": m, "n": n, "agreement": round(agree / n, 3) if n else 0, "false_go": m["NO-GO"]["GO"]}
