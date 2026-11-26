"""M6 / M6i core logic (pure Python, unit-tested):
dedupe -> chunk (keeping card id) -> hybrid search (BM25 + vectors, RRF)
-> rerank -> filters. The Postgres backend (pg.py) uses the same pieces."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional
from urllib.parse import urlparse, urlunparse

import numpy as np

from common.text import tokenize


# ------------------------------------------------------------------ dedupe
def normalise_url(url: str) -> str:
    p = urlparse(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.")
    path = p.path.rstrip("/")
    return urlunparse(("https", host, path, "", p.query if "ycombinator" in host else "", ""))


def content_key(card: dict) -> str:
    return " ".join(tokenize(f"{card.get('name', '')} {card.get('summary', '')}"))[:200]


def dedupe(new_cards: Iterable[dict], seen_urls: set[str], seen_keys: set[str]) -> tuple[list[dict], int]:
    """Repeatable without duplicates: same normalised URL or same name+summary
    => skip. Returns (cards to add, number dropped)."""
    out, dropped = [], 0
    for c in new_cards:
        u, k = normalise_url(c["url"]), content_key(c)
        if u in seen_urls or (k and k in seen_keys):
            dropped += 1
            continue
        seen_urls.add(u)
        if k:
            seen_keys.add(k)
        out.append(c)
    return out, dropped


# ------------------------------------------------------------------ chunk
def chunk(card: dict, max_words: int = 120, overlap: int = 20) -> list[dict]:
    """Split card text into chunks. Every chunk keeps its card id so every
    citation can be traced back: evidence_id = <card_id>#c<n>."""
    words = (card.get("text") or f"{card.get('name', '')}. {card.get('summary', '')}").split()
    chunks, i, n = [], 0, 0
    while i < max(len(words), 1):
        piece = " ".join(words[i:i + max_words])
        chunks.append({"chunk_id": f"{card['id']}#c{n}", "card_id": card["id"], "text": piece,
                       "source": card["source"], "url": card["url"],
                       "published_at": card.get("published_at"),
                       "niche": (card.get("niche_tags") or ["unknown"])[0]})
        n += 1
        i += max_words - overlap
        if i >= len(words):
            break
    return chunks


# ------------------------------------------------------------------ BM25
class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: list[Counter] = []
        self.lens: list[int] = []
        self.df: Counter = Counter()

    def add(self, text: str) -> None:
        toks = tokenize(text)
        c = Counter(toks)
        self.docs.append(c)
        self.lens.append(len(toks))
        self.df.update(c.keys())

    def scores(self, query: str) -> np.ndarray:
        N = len(self.docs)
        avg = (sum(self.lens) / N) if N else 1
        s = np.zeros(N)
        for q in set(tokenize(query)):
            df = self.df.get(q, 0)
            if not df:
                continue
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            for i, d in enumerate(self.docs):
                f = d.get(q, 0)
                if f:
                    s[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.lens[i] / avg))
        return s


# ------------------------------------------------------------------ fusion
def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion of several ranked lists of doc indices."""
    score: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            score[doc] += 1.0 / (k + rank + 1)
    return sorted(score.items(), key=lambda x: -x[1])


@dataclass
class Filters:
    source: Optional[list[str]] = None
    niche: Optional[list[str]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None

    def ok(self, ch: dict) -> bool:
        if self.source and ch["source"] not in self.source:
            return False
        if self.niche and ch["niche"] not in self.niche:
            return False
        d = ch.get("published_at") or ""
        if self.date_from and (not d or d < self.date_from):
            return False
        if self.date_to and (not d or d > self.date_to):
            return False
        return True


Embedder = Callable[[list[str]], np.ndarray]
Reranker = Callable[[str, list[str]], list[float]]


@dataclass
class InMemoryIndex:
    """Hybrid index used in tests, CI retrieval gate and as a no-DB fallback."""
    embed: Embedder
    rerank: Optional[Reranker] = None
    chunks: list[dict] = field(default_factory=list)
    bm25: BM25 = field(default_factory=BM25)
    vecs: Optional[np.ndarray] = None

    def add_cards(self, cards: list[dict]) -> int:
        new = [ch for c in cards for ch in chunk(c)]
        for ch in new:
            self.bm25.add(ch["text"])
        v = self.embed([ch["text"] for ch in new])
        self.vecs = v if self.vecs is None else np.vstack([self.vecs, v])
        self.chunks += new
        return len(new)

    def search(self, query: str, k: int = 8, filters: Optional[Filters] = None,
               mode: str = "hybrid", candidates: int = 50) -> list[dict]:
        if not self.chunks:
            return []
        f = filters or Filters()
        allowed = np.array([f.ok(ch) for ch in self.chunks])
        rankings = []
        if mode in ("hybrid", "keyword"):
            s = np.where(allowed, self.bm25.scores(query), -1)
            rankings.append([i for i in np.argsort(-s)[:candidates] if s[i] > 0])
        if mode in ("hybrid", "vector"):
            q = self.embed([query])[0]
            s = np.where(allowed, self.vecs @ q, -2)
            rankings.append([i for i in np.argsort(-s)[:candidates] if allowed[i]])
        fused = rrf(rankings)[:candidates]
        idx = [i for i, _ in fused]
        if self.rerank and mode == "hybrid" and idx:
            rs = self.rerank(query, [self.chunks[i]["text"] for i in idx])
            idx = [i for _, i in sorted(zip(rs, idx), key=lambda x: -x[0])]
        out, seen_cards = [], set()
        for i in idx:  # one best chunk per card
            ch = self.chunks[i]
            if ch["card_id"] in seen_cards:
                continue
            seen_cards.add(ch["card_id"])
            out.append({**ch, "evidence_id": ch["chunk_id"], "quote": ch["text"][:300]})
            if len(out) == k:
                break
        return out


# ------------------------------------------------------------------ retrieval metrics
def recall_at_k(results: list[str], relevant: set[str], k: int) -> float:
    return len(set(results[:k]) & relevant) / max(1, len(relevant))


def mrr(results: list[str], relevant: set[str]) -> float:
    for i, r in enumerate(results):
        if r in relevant:
            return 1 / (i + 1)
    return 0.0


# ------------------------------------------------------------------ freshness / coverage
def freshness_report(cards: list[dict], today: str) -> dict:
    from datetime import date
    by_src: dict[str, list[str]] = defaultdict(list)
    niches: Counter = Counter()
    for c in cards:
        by_src[c["source"]].append(c.get("fetched_at") or "")
        niches[(c.get("niche_tags") or ["unknown"])[0]] += 1
    t = date.fromisoformat(today)
    src = {s: {"cards": len(v), "newest_fetch": max(v),
               "age_days": (t - date.fromisoformat(max(v))).days if max(v) else None}
           for s, v in by_src.items()}
    return {"sources": src, "total_cards": len(cards), "niches": dict(niches.most_common()),
            "n_niches": len(niches)}
