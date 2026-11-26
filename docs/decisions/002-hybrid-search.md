# DDR-002: Hybrid search (BM25 + vectors, fused with RRF, then cross-encoder rerank)

- **Status:** Accepted
- **Context:** Vector search alone can miss exact product names, and keyword search alone misses paraphrases ("timetable clash" vs "overlapping exams").
- **Options:** (1) vector only, (2) keyword only (Postgres full-text), (3) hybrid with reciprocal rank fusion and reranking.
- **Decision:** Hybrid. Postgres `tsvector` for keywords and `pgvector` HNSW for vectors, reciprocal rank fusion (k=60), then `cross-encoder/ms-marco-MiniLM-L-6-v2` reranking of the top 50.
- **Why:** On our 20 hand-written queries against the real KB: recall@5 keyword = __, vector = __, hybrid = __ (fill in from `scripts/eval_retrieval_live.py`; the CI fixture only checks for regressions).
- **Cost:** About __ ms more per query for reranking (measure it). Postgres holds both indexes, so there is no extra vector-database service to run.
- **AI use:** Drafted with AI help. We measured and filled in the numbers ourselves.
