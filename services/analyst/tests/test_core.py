from datetime import date

import numpy as np

from src.core import classify, find_gaps, kmeans, last_n_months, monthly_series, slope


def test_kmeans_separates_two_groups():
    X = np.array([[1, 0], [0.99, 0.1], [0, 1], [0.1, 0.99]], dtype=float)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    l = kmeans(X, 2)
    assert l[0] == l[1] and l[2] == l[3] and l[0] != l[2]


def test_last_n_months_wraps_year():
    assert last_n_months(date(2026, 2, 5), 3) == ["2025-12", "2026-01", "2026-02"]


def test_series_and_slope_rising():
    cards = [{"source": "reddit", "published_at": f"2026-{m:02d}-01"} for m in range(1, 7) for _ in range(m)]
    s = monthly_series(cards, [f"2026-{m:02d}" for m in range(1, 7)])
    vals = [v["mentions"] for v in s.values()]
    assert vals == [1, 2, 3, 4, 5, 6] and slope(vals) > 0.05


def test_classify():
    assert classify(0.2, 10, 0) == "rising"
    assert classify(-0.1, 100, 5) == "saturated"
    assert classify(0.0, 10, 0) == "flat"


def test_find_gaps_uses_complaints_not_covered():
    cards = [
        {"id": "c1", "source": "reddit", "text": "I hate that exam timetables clash and nobody warns students."},
        {"id": "c2", "source": "github", "name": "todo", "summary": "a todo list"},
    ]
    g = find_gaps(cards)
    assert g and g[0]["evidence_ids"] == ["c1#c0"]
