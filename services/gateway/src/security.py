"""Passwords (scrypt, stdlib), JWT tokens and rate limiting for M1."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional, Protocol

SECRET = os.environ.get("JWT_SECRET", "")
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "86400"))


# ---------------------------------------------------------------- passwords
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, s, d = stored.split("$")
        dk = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(dk, base64.b64decode(d))
    except Exception:
        return False


# ---------------------------------------------------------------- JWT (HS256, no extra dependency)
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: str, secret: str = "", now: Optional[float] = None) -> str:
    secret = secret or SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET is not set")
    now = now or time.time()
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps({"sub": user_id, "iat": int(now), "exp": int(now + TOKEN_TTL)}).encode())
    sig = _b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def read_token(token: str, secret: str = "", now: Optional[float] = None) -> Optional[str]:
    secret = secret or SECRET
    try:
        head, body, sig = token.split(".")
        good = _b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        claims = json.loads(_unb64(body))
        if claims["exp"] < (now or time.time()):
            return None
        return claims["sub"]
    except Exception:
        return None


# ---------------------------------------------------------------- rate limiting
class Counter(Protocol):
    def incr(self, key: str, ttl: int) -> int: ...


class MemoryCounter:
    def __init__(self):
        self.d: dict[str, tuple[int, float]] = {}

    def incr(self, key: str, ttl: int) -> int:
        n, exp = self.d.get(key, (0, time.time() + ttl))
        if time.time() > exp:
            n, exp = 0, time.time() + ttl
        self.d[key] = (n + 1, exp)
        return n + 1


class RedisCounter:
    """Shared across gateway replicas (the gateway autoscales)."""

    def __init__(self, url: str):
        import redis
        self.r = redis.Redis.from_url(url)

    def incr(self, key: str, ttl: int) -> int:
        p = self.r.pipeline()
        p.incr(key)
        p.expire(key, ttl, nx=True)
        return p.execute()[0]


LIMITS = {  # requests per minute
    "default": int(os.environ.get("RATE_DEFAULT", "120")),
    "runs": int(os.environ.get("RATE_RUNS", "10")),     # /discover, /validate start paid work
    "auth": int(os.environ.get("RATE_AUTH", "10")),
}


def allowed(counter: Counter, who: str, bucket: str, now: Optional[float] = None) -> bool:
    window = int((now or time.time()) // 60)
    return counter.incr(f"rl:{bucket}:{who}:{window}", 70) <= LIMITS[bucket]
