-- M2 application data. Applied in order by src/migrate.py; each file runs once
-- (tracked in schema_migrations).
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,
  email       TEXT UNIQUE NOT NULL,
  hash        TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profiles (
  user_id         TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  skills          TEXT[] DEFAULT '{}',
  hours_per_week  REAL NOT NULL DEFAULT 10,
  weeks_available INT  NOT NULL DEFAULT 12,
  team_size       INT  NOT NULL DEFAULT 1,
  compute         TEXT NOT NULL DEFAULT 'laptop',
  goal            TEXT NOT NULL DEFAULT 'course_project',
  interests       TEXT[] DEFAULT '{}',
  version         INT  NOT NULL DEFAULT 1,   -- part of every cache key
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ideas (
  id          TEXT PRIMARY KEY,
  user_id     TEXT REFERENCES users(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT 'own',   -- own | generated
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idea_versions (
  idea_id     TEXT REFERENCES ideas(id) ON DELETE CASCADE,
  version     INT NOT NULL,
  text        TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (idea_id, version)
);

CREATE TABLE IF NOT EXISTS verdicts (
  id          SERIAL PRIMARY KEY,
  idea_id     TEXT NOT NULL,
  version     INT NOT NULL,
  run_id      TEXT NOT NULL,
  verdict     TEXT NOT NULL,
  stability   TEXT,
  score       REAL,
  confidence  REAL,
  card        JSONB NOT NULL,
  rubric_set  TEXT,
  created_at  TIMESTAMPTZ DEFAULT now(),
  FOREIGN KEY (idea_id, version) REFERENCES idea_versions(idea_id, version) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dimension_scores (
  verdict_id  INT REFERENCES verdicts(id) ON DELETE CASCADE,
  dimension   TEXT NOT NULL,
  score       REAL,
  conf        REAL,
  evidence    TEXT[],
  PRIMARY KEY (verdict_id, dimension)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id      TEXT PRIMARY KEY,
  user_id     TEXT,
  kind        TEXT,                 -- validate | discover
  status      TEXT,
  result      JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approvals (
  run_id    TEXT,
  action    TEXT,
  decision  TEXT,
  decided_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
  idea_id  TEXT REFERENCES ideas(id) ON DELETE CASCADE,
  turns    JSONB DEFAULT '[]'
);
