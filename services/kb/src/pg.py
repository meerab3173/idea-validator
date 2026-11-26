"""Postgres + pgvector repository for the knowledge base."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date
from typing import Optional

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from .core import Filters, chunk, content_key, dedupe, normalise_url, rrf

DSN = os.environ.get("KB_DATABASE_URL", os.environ.get("DATABASE_URL", ""))


def connect():
    conn = psycopg.connect(DSN, autocommit=True)
    register_vector(conn)
    return conn


def migrate(conn) -> None:
    here = os.path.dirname(__file__)
    for f in sorted(os.listdir(os.path.join(here, "..", "migrations"))):
        with open(os.path.join(here, "..", "migrations", f)) as fh:
            conn.execute(fh.read())


class KBRepo:
    def __init__(self, conn, embed, rerank=None):
        self.conn, self.embed, self.rerank = conn, embed, rerank

    # ---------------------------------------------------------- ingestion (M6i)
    def ingest(self, source: str, cards: list[dict]) -> dict:
        urls = {r[0] for r in self.conn.execute("SELECT url_norm FROM cards")}
        keys = {r[0] for r in self.conn.execute("SELECT content_key FROM cards WHERE content_key <> ''")}
        new, dropped = dedupe(cards, urls, keys)
        today = date.today().isoformat()
        for c in new:
            self.conn.execute(
                """INSERT INTO cards (id,name,one_liner,problem,customer,niche,niche_tags,stage,
                   funding_usd,url_norm,content_key,published_at,author,raw)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (c["id"], c["name"], c.get("summary"), c.get("problem"), c.get("customer"),
                 (c.get("niche_tags") or ["unknown"])[0], c.get("niche_tags") or [],
                 c.get("stage", "unknown"), c.get("funding_usd"), normalise_url(c["url"]),
                 content_key(c), c.get("published_at"), c.get("author"), json.dumps(c)))
            self.conn.execute(
                "INSERT INTO card_sources VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (c["id"], c["source"], c["url"], c.get("fetched_at") or today))
            chs = chunk(c)
            vecs = self.embed([ch["text"] for ch in chs])
            with self.conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO chunks (chunk_id,card_id,text,source,niche,published_at,embedding)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    [(ch["chunk_id"], ch["card_id"], ch["text"], ch["source"], ch["niche"],
                      ch["published_at"], v) for ch, v in zip(chs, vecs)])
        run_id = f"ing_{uuid.uuid4().hex[:8]}"
        self.conn.execute("INSERT INTO ingestion_runs (run_id,source,added,dropped) VALUES (%s,%s,%s,%s)",
                          (run_id, source, len(new), dropped))
        return {"run_id": run_id, "added": len(new), "dropped": dropped}

    # ---------------------------------------------------------- search
    def _where(self, f: Filters) -> tuple[str, list]:
        sql, args = [], []
        if f.source:
            sql.append("source = ANY(%s)"); args.append(f.source)
        if f.niche:
            sql.append("niche = ANY(%s)"); args.append(f.niche)
        if f.date_from:
            sql.append("published_at >= %s"); args.append(f.date_from)
        if f.date_to:
            sql.append("published_at <= %s"); args.append(f.date_to)
        return (" AND " + " AND ".join(sql)) if sql else "", args

    def search(self, query: str, k: int = 8, filters: Optional[Filters] = None,
               mode: str = "hybrid", candidates: int = 50) -> list[dict]:
        f = filters or Filters()
        where, args = self._where(f)
        rows: dict[str, tuple] = {}
        rankings = []
        if mode in ("hybrid", "keyword"):
            kw = self.conn.execute(
                f"""SELECT chunk_id, card_id, text, source, niche, published_at
                    FROM chunks WHERE tsv @@ websearch_to_tsquery('english', %s) {where}
                    ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) DESC LIMIT %s""",
                [query, *args, query, candidates]).fetchall()
            rankings.append([r[0] for r in kw]); rows.update({r[0]: r for r in kw})
        if mode in ("hybrid", "vector"):
            q = np.asarray(self.embed([query])[0])
            vv = self.conn.execute(
                f"""SELECT chunk_id, card_id, text, source, niche, published_at
                    FROM chunks WHERE TRUE {where} ORDER BY embedding <=> %s LIMIT %s""",
                [*args, q, candidates]).fetchall()
            rankings.append([r[0] for r in vv]); rows.update({r[0]: r for r in vv})
        ids = [i for i, _ in rrf(rankings)][:candidates]
        if self.rerank and mode == "hybrid" and ids:
            sc = self.rerank(query, [rows[i][2] for i in ids])
            ids = [i for _, i in sorted(zip(sc, ids), key=lambda x: -x[0])]
        urls = dict(self.conn.execute(
            "SELECT card_id, url FROM card_sources WHERE card_id = ANY(%s)",
            [[rows[i][1] for i in ids]]).fetchall()) if ids else {}
        out, seen = [], set()
        for i in ids:
            cid, card, text, src, niche, pub = rows[i]
            if card in seen:
                continue
            seen.add(card)
            out.append({"evidence_id": cid, "card_id": card, "quote": text[:300], "source": src,
                        "niche": niche, "published_at": str(pub) if pub else None,
                        "url": urls.get(card, "")})
            if len(out) == k:
                break
        return out

    # ---------------------------------------------------------- reporting
    def stats(self) -> dict:
        per = dict(self.conn.execute("SELECT platform, count(*) FROM card_sources GROUP BY 1").fetchall())
        fresh = {p: str(d) for p, d in self.conn.execute(
            "SELECT platform, max(fetched_at) FROM card_sources GROUP BY 1").fetchall()}
        niches = self.conn.execute("SELECT count(DISTINCT niche) FROM cards").fetchone()[0]
        total = self.conn.execute("SELECT count(*) FROM cards").fetchone()[0]
        return {"total_cards": total, "cards_per_source": per, "newest_fetch": fresh, "n_niches": niches}

    def all_cards(self) -> list[dict]:
        return [r[0] for r in self.conn.execute("SELECT raw FROM cards")]

    def evidence_exists(self, ids: list[str]) -> dict[str, Optional[str]]:
        rows = dict(self.conn.execute("SELECT chunk_id, text FROM chunks WHERE chunk_id = ANY(%s)", [ids]).fetchall())
        return {i: rows.get(i) for i in ids}
