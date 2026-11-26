-- M6 knowledge base schema (Postgres 16 + pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS cards (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  one_liner     TEXT,
  problem       TEXT,
  customer      TEXT,
  niche         TEXT,
  niche_tags    TEXT[] DEFAULT '{}',
  stage         TEXT DEFAULT 'unknown',
  funding_usd   DOUBLE PRECISION,
  url_norm      TEXT UNIQUE NOT NULL,
  content_key   TEXT,
  published_at  DATE,
  author        TEXT,
  raw           JSONB
);
CREATE INDEX IF NOT EXISTS cards_content_key ON cards(content_key);

CREATE TABLE IF NOT EXISTS card_sources (
  card_id     TEXT REFERENCES cards(id) ON DELETE CASCADE,
  platform    TEXT NOT NULL,
  url         TEXT NOT NULL,
  fetched_at  DATE NOT NULL,
  PRIMARY KEY (card_id, platform)
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id     TEXT PRIMARY KEY,           -- <card_id>#c<n>
  card_id      TEXT REFERENCES cards(id) ON DELETE CASCADE,
  text         TEXT NOT NULL,
  source       TEXT NOT NULL,
  niche        TEXT,
  published_at DATE,
  embedding    vector(384),
  tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_vec ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_filters ON chunks (source, niche, published_at);

CREATE TABLE IF NOT EXISTS niches (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  size        INT,
  trend_slope DOUBLE PRECISION,
  status      TEXT,                -- rising | flat | saturated
  keywords    TEXT[]
);

CREATE TABLE IF NOT EXISTS niche_stats (
  niche_id  TEXT REFERENCES niches(id) ON DELETE CASCADE,
  month     DATE,
  launches  INT,
  mentions  INT,
  PRIMARY KEY (niche_id, month)
);

CREATE TABLE IF NOT EXISTS gaps (
  id          SERIAL PRIMARY KEY,
  niche_id    TEXT REFERENCES niches(id) ON DELETE CASCADE,
  description TEXT,
  evidence_ids TEXT[],
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  run_id     TEXT PRIMARY KEY,
  source     TEXT,
  added      INT,
  dropped    INT,
  started_at TIMESTAMPTZ DEFAULT now()
);
