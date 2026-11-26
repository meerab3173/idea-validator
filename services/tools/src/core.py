"""M5 Tool Layer: the single controlled exit to the internet.
allow-list -> robots.txt -> per-domain rate limit -> cache -> fetch -> sanitise."""
from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

USER_AGENT = "FAST-CS4032-IdeaValidator/1.0 (student project; contact: see README)"

DEFAULT_ALLOW = {
    "hacker-news.firebaseio.com": 5.0,   # requests per second
    "hn.algolia.com": 2.0,
    "api.github.com": 0.5,
    "www.reddit.com": 0.5,
    "oauth.reddit.com": 0.5,
    "api.producthunt.com": 0.5,
    "api.ycombinator.com": 0.5,
    "yc-oss.github.io": 1.0,
}


class Blocked(Exception):
    pass


# ---------------------------------------------------------------- allow-list
def check_allowed(url: str, allow: dict[str, float]) -> str:
    p = urlparse(url)
    if p.scheme != "https":
        raise Blocked(f"only https allowed: {url}")
    host = (p.hostname or "").lower()
    if host not in allow:
        raise Blocked(f"domain not on allow-list: {host}")
    return host


# ---------------------------------------------------------------- rate limit
@dataclass
class TokenBucket:
    rate: float              # tokens per second
    capacity: float = 2.0
    tokens: float = 2.0
    last: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, now: Optional[float] = None) -> float:
        """Returns seconds to wait (0 if a token was available)."""
        with self.lock:
            now = time.monotonic() if now is None else now
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0
            return (1 - self.tokens) / self.rate


class RateLimiter:
    def __init__(self, allow: dict[str, float]):
        self.buckets = {h: TokenBucket(rate=r) for h, r in allow.items()}

    def wait(self, host: str, sleep: Callable[[float], None] = time.sleep) -> float:
        waited = 0.0
        while True:
            w = self.buckets[host].take()
            if w <= 0:
                return waited
            sleep(w)
            waited += w


# ---------------------------------------------------------------- robots.txt
class Robots:
    """robots.txt per host, cached for 24h. APIs without robots.txt => allowed."""

    def __init__(self, fetch_text: Callable[[str], Optional[str]]):
        self.fetch_text = fetch_text
        self.cache: dict[str, tuple[float, RobotFileParser]] = {}

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        host = p.hostname or ""
        hit = self.cache.get(host)
        if not hit or time.time() - hit[0] > 86400:
            rp = RobotFileParser()
            txt = self.fetch_text(f"{p.scheme}://{host}/robots.txt")
            rp.parse((txt or "").splitlines())
            self.cache[host] = (time.time(), rp)
        return self.cache[host][1].can_fetch(USER_AGENT, url)


# ---------------------------------------------------------------- cache
class TTLCache:
    def __init__(self, ttl: int = 3600):
        self.ttl, self.data = ttl, {}

    def get(self, k: str):
        v = self.data.get(k)
        if v and time.time() - v[0] < self.ttl:
            return v[1]
        return None

    def set(self, k: str, v) -> None:
        self.data[k] = (time.time(), v)


# ---------------------------------------------------------------- sanitiser
INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |the )?(previous|prior|above)",
    r"you are now [a-z ]{0,30}",
    r"(new|updated) instructions?:",
    r"\bsystem prompt\b",
    r"\b(assistant|system)\s*:",
    r"rate this (idea|product) (a )?(5|five|10)",
    r"give (this|it) (a )?(score|rating) of",
    r"always (answer|reply|respond|output)",
    r"do not (tell|reveal|mention)",
    r"<\s*/?\s*(system|instructions?|prompt)\s*>",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)
_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)
_ZERO_WIDTH = re.compile("[​-‏⁠﻿]")


@dataclass
class Sanitised:
    text: str
    removed: list[str]

    @property
    def flagged(self) -> bool:
        return bool(self.removed)


def sanitise(raw: str, max_chars: int = 20000) -> Sanitised:
    """Strip HTML, invisible characters and instructions aimed at models.
    Fetched text is DATA: whatever survives is still never obeyed (M12)."""
    t = _TAGS.sub(" ", raw)
    t = html.unescape(t)
    t = _ZERO_WIDTH.sub("", t)
    removed = [m.group(0) for m in _INJ.finditer(t)]
    t = _INJ.sub("[removed: instruction-like text]", t)
    t = re.sub(r"\s+", " ", t).strip()
    return Sanitised(t[:max_chars], removed)
