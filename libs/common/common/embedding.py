"""Embedding + reranking models. Real models from sentence-transformers
(CPU-friendly). If the library is not installed (e.g. CI), a hashing
embedder is used so tests still run; it is clearly logged."""
from __future__ import annotations

import hashlib
import logging
import os

import numpy as np

from .text import tokenize

log = logging.getLogger("kb.embed")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
DIM = 384


def hashing_embed(texts: list[str]) -> np.ndarray:
    """Deterministic bag-of-words hashing vectors (fallback only)."""
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in tokenize(t):
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            out[i, h % DIM] += 1.0 if (h >> 8) % 2 else -1.0
        n = np.linalg.norm(out[i])
        if n:
            out[i] /= n
    return out


def get_embedder():
    if os.environ.get("EMBEDDER", "st") == "hash":
        return hashing_embed
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(EMBED_MODEL, device="cpu")
        return lambda texts: m.encode(texts, normalize_embeddings=True, batch_size=64,
                                      show_progress_bar=False).astype(np.float32)
    except Exception as e:  # noqa: BLE001
        log.warning("sentence-transformers unavailable (%s); using hashing embedder", e)
        return hashing_embed


def get_reranker():
    if os.environ.get("RERANK", "on") == "off":
        return None
    try:
        from sentence_transformers import CrossEncoder
        m = CrossEncoder(RERANK_MODEL, device="cpu")
        return lambda q, docs: m.predict([(q, d) for d in docs]).tolist()
    except Exception as e:  # noqa: BLE001
        log.warning("reranker unavailable (%s); skipping rerank", e)
        return None
