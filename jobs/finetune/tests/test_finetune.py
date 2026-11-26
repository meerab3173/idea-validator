import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[3] / "libs/common")]
from compare import score_row, summarise  # noqa: E402
from split import split  # noqa: E402


def rows(n_ideas, per=6, checked=()):
    return [{"idea_id": f"i{i}", "checked": f"i{i}" in checked} for i in range(n_ideas) for _ in range(per)]


def test_split_by_idea_no_leak_and_checked_in_test():
    tr, te = split(rows(50, checked={"i1", "i2"}))
    assert not ({r["idea_id"] for r in tr} & {r["idea_id"] for r in te})
    assert {"i1", "i2"} <= {r["idea_id"] for r in te}
    assert 0.15 < len(te) / (len(tr) + len(te)) < 0.25


def test_score_row():
    h = {"score": 3, "evidence_ids": ["a#c0"]}
    r = score_row('{"score": 4, "confidence": 0.6, "evidence_ids": ["a#c0", "fake#c1"], "reason": "x"}', h, ["a#c0"])
    assert r == {"valid": True, "abs_err": 1.0, "real_ids": 0.5}
    assert score_row("not json", h, [])["valid"] is False


def test_summarise():
    s = summarise([{"valid": True, "abs_err": 0.5, "real_ids": 1.0}, {"valid": False, "abs_err": None, "real_ids": None}], [0.1, 0.3], 0.002)
    assert s["valid_json"] == 0.5 and s["within_1"] == 0.5 and s["latency_ms"] == 200
