"""M4 Scout agents. Each source = URL builder + parser to raw idea cards.
Network goes ONLY through M5 (`fetch` is injected, it calls POST tools:/fetch)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Iterable
from urllib.parse import quote_plus

Fetch = Callable[[str], dict]  # url -> {"json": ...}


def card_id(source: str, url: str) -> str:
    return "card_" + hashlib.sha1(f"{source}|{url}".encode()).hexdigest()[:10]


def _date(ts) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    return str(ts)[:10]


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ------------------------------------------------------------------ Hacker News (Algolia API)
def hn_urls(query: str = "", pages: int = 5, tags: str = "show_hn") -> list[str]:
    q = quote_plus(query)
    return [f"https://hn.algolia.com/api/v1/search_by_date?tags={tags}&query={q}&hitsPerPage=100&page={p}"
            for p in range(pages)]


def parse_hn(data: dict) -> list[dict]:
    out = []
    for h in data.get("hits", []):
        title = h.get("title") or h.get("story_title") or ""
        if not title:
            continue
        url = f"https://news.ycombinator.com/item?id={h['objectID']}"
        text = " ".join(filter(None, [title, h.get("story_text") or h.get("comment_text") or ""]))
        name = title.replace("Show HN:", "").replace("Ask HN:", "").split("–")[0].split(" - ")[0].strip()
        out.append({"id": card_id("hackernews", url), "name": name[:120], "summary": title[:300],
                    "source": "hackernews", "url": url, "published_at": _date(h.get("created_at_i")),
                    "fetched_at": today(), "text": text[:8000], "stage": "launched",
                    "author": h.get("author"), "points": h.get("points") or 0})
    return out


# ------------------------------------------------------------------ GitHub (REST search)
def github_urls(query: str = "topic:saas", pages: int = 5) -> list[str]:
    q = quote_plus(f"{query} stars:>20")
    return [f"https://api.github.com/search/repositories?q={q}&sort=updated&per_page=100&page={p + 1}"
            for p in range(pages)]


def parse_github(data: dict) -> list[dict]:
    out = []
    for r in data.get("items", []):
        url = r["html_url"]
        desc = r.get("description") or ""
        out.append({"id": card_id("github", url), "name": r["name"], "summary": desc[:300],
                    "niche_tags": (r.get("topics") or [])[:8], "source": "github", "url": url,
                    "published_at": _date(r.get("created_at")), "fetched_at": today(),
                    "text": f"{r['name']}. {desc} Topics: {', '.join(r.get('topics') or [])}",
                    "stage": "launched", "author": (r.get("owner") or {}).get("login"),
                    "stars": r.get("stargazers_count", 0)})
    return out


# ------------------------------------------------------------------ YC directory (yc-oss open dataset)
def yc_urls(**_) -> list[str]:
    return ["https://yc-oss.github.io/api/companies/all.json"]


def parse_yc(data) -> list[dict]:
    out = []
    for c in data if isinstance(data, list) else []:
        url = c.get("url") or f"https://www.ycombinator.com/companies/{c.get('slug', '')}"
        out.append({"id": card_id("yc", url), "name": c.get("name", ""),
                    "summary": (c.get("one_liner") or "")[:300],
                    "niche_tags": [t.lower() for t in (c.get("tags") or [])][:8],
                    "customer": ", ".join(c.get("industries") or []),
                    "stage": (c.get("stage") or "unknown").lower(), "source": "yc", "url": url,
                    "published_at": _date(c.get("launched_at")),
                    "fetched_at": today(),
                    "text": f"{c.get('name', '')}. {c.get('one_liner') or ''} {c.get('long_description') or ''}"[:8000],
                    "batch": c.get("batch")})
    return out


# ------------------------------------------------------------------ Reddit (official API, OAuth token in M5)
def reddit_urls(subs: Iterable[str] = ("SideProject", "startups", "SaaS", "Entrepreneur"),
                pages: int = 1, **_) -> list[str]:
    return [f"https://oauth.reddit.com/r/{s}/top?t=year&limit=100" for s in subs]


def parse_reddit(data: dict) -> list[dict]:
    out = []
    for ch in (data.get("data") or {}).get("children", []):
        p = ch.get("data", {})
        url = "https://www.reddit.com" + p.get("permalink", "")
        out.append({"id": card_id("reddit", url), "name": (p.get("title") or "")[:120],
                    "summary": (p.get("title") or "")[:300], "source": "reddit", "url": url,
                    "niche_tags": [p.get("subreddit", "").lower()],
                    "published_at": _date(p.get("created_utc")), "fetched_at": today(),
                    "text": f"{p.get('title', '')}. {p.get('selftext', '')}"[:8000],
                    "author": p.get("author"), "points": p.get("score", 0)})
    return out


SOURCES = {
    "hn": (hn_urls, parse_hn),
    "github": (github_urls, parse_github),
    "yc": (yc_urls, parse_yc),
    "reddit": (reddit_urls, parse_reddit),
}


def run_source(name: str, fetch: Fetch, **kw) -> dict:
    """Run one source with failure handling: a failing page is logged and
    skipped, a failing source does not stop the others."""
    urls_fn, parse = SOURCES[name]
    cards, errors = [], []
    for url in urls_fn(**kw):
        try:
            cards += parse(fetch(url)["json"])
        except Exception as e:  # noqa: BLE001 - we record every failure
            errors.append(f"{url}: {e!r}")
    return {"source": name, "cards": cards, "errors": errors}
