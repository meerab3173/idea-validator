"""M7 Niche and Trend Analyst: cluster cards into named niches, monthly time
series, rising / flat / saturated, and a list of gaps for M8 and M9."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import date

import numpy as np

COMPLAINT = re.compile(
    r"\b(slow|wish|missing|hate|annoying|can't|cannot|no way to|struggl\w*|frustrat\w*|"
    r"lack\w*|expensive|broken|painful|waste|lose|lost|forget|complain\w*)\b", re.I)
PRODUCT_SOURCES = {"github", "yc", "producthunt"}
VOICE_SOURCES = {"reddit", "hackernews"}


def kmeans(X: np.ndarray, k: int, iters: int = 50, seed: int = 42) -> np.ndarray:
    """Plain k-means (cosine on normalised vectors). Deterministic via seed."""
    rng = np.random.default_rng(seed)
    k = min(k, len(X))
    C = X[rng.choice(len(X), k, replace=False)]
    labels = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        new = np.argmax(X @ C.T, axis=1)
        if np.array_equal(new, labels) and _ > 0:
            break
        labels = new
        for j in range(k):
            m = X[labels == j]
            if len(m):
                c = m.mean(0)
                C[j] = c / (np.linalg.norm(c) or 1)
    return labels


def name_clusters(texts: list[str], labels: np.ndarray, tokenize, top: int = 3) -> dict[int, list[str]]:
    """Name each cluster by the words most specific to it (tf-idf style)."""
    df: Counter = Counter()
    per: dict[int, Counter] = defaultdict(Counter)
    for t, l in zip(texts, labels):
        toks = set(tokenize(t))
        df.update(toks)
        per[int(l)].update(toks)
    N = len(texts)
    names = {}
    for l, c in per.items():
        scored = sorted(c.items(), key=lambda kv: -kv[1] * math.log(N / (1 + df[kv[0]])))
        names[l] = [w for w, _ in scored[:top]]
    return names


def month(d: str | None) -> str | None:
    return d[:7] if d and len(d) >= 7 else None


def monthly_series(cards: list[dict], months: list[str]) -> dict[str, dict[str, int]]:
    out = {m: {"launches": 0, "mentions": 0} for m in months}
    for c in cards:
        m = month(c.get("published_at"))
        if m in out:
            key = "launches" if c["source"] in PRODUCT_SOURCES else "mentions"
            out[m][key] += 1
    return out


def slope(values: list[float]) -> float:
    if len(values) < 2 or not any(values):
        return 0.0
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    m = np.polyfit(x, y, 1)[0]
    return float(m / (y.mean() or 1))  # relative slope per month


def classify(rel_slope: float, size: int, launches_recent: int, sat_size: int = 60) -> str:
    if rel_slope > 0.05:
        return "rising"
    if size >= sat_size and rel_slope <= 0.0 and launches_recent >= 3:
        return "saturated"
    return "flat"


def last_n_months(today: date, n: int = 12) -> list[str]:
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def find_gaps(niche_cards: list[dict], max_gaps: int = 5) -> list[dict]:
    """A gap = a complaint from users (reddit/HN) whose key words are not
    covered by any product description in the same niche."""
    products = " ".join(f"{c.get('name', '')} {c.get('summary', '')}".lower()
                        for c in niche_cards if c["source"] in PRODUCT_SOURCES)
    gaps = []
    for c in niche_cards:
        if c["source"] not in VOICE_SOURCES:
            continue
        txt = c.get("text") or ""
        for sent in re.split(r"(?<=[.!?])\s+", txt):
            if not COMPLAINT.search(sent):
                continue
            words = [w for w in re.findall(r"[a-z]{5,}", sent.lower())]
            covered = sum(1 for w in words if w in products) / max(1, len(words))
            if covered < 0.3:
                gaps.append({"description": sent.strip()[:240], "evidence_ids": [f"{c['id']}#c0"],
                             "coverage": round(covered, 2)})
                break
    gaps.sort(key=lambda g: g["coverage"])
    return gaps[:max_gaps]


def analyse(cards: list[dict], embed, tokenize, k: int = 12, today: date | None = None) -> dict:
    today = today or date.today()
    texts = [f"{c.get('name', '')}. {c.get('summary', '')}. {c.get('text', '')[:500]}" for c in cards]
    X = embed(texts)
    labels = kmeans(X, k)
    names = name_clusters(texts, labels, tokenize)
    months = last_n_months(today)
    niches = []
    for l in sorted(set(labels.tolist())):
        members = [c for c, x in zip(cards, labels) if x == l]
        series = monthly_series(members, months)
        total = [v["launches"] + v["mentions"] for v in series.values()]
        sl = slope(total)
        recent = sum(series[m]["launches"] for m in months[-3:])
        nid = f"niche_{l}"
        niches.append({
            "id": nid, "name": " / ".join(names[l]), "keywords": names[l], "size": len(members),
            "trend_slope": round(sl, 3), "status": classify(sl, len(members), recent),
            "series": series, "card_ids": [c["id"] for c in members],
            "gaps": find_gaps(members),
        })
    return {"niches": niches, "assignments": {c["id"]: f"niche_{l}" for c, l in zip(cards, labels.tolist())}}
