"""Small factory every service uses: FastAPI app with /health, /ready and
/metrics (Prometheus text format), plus JSON request logging."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

ReadyCheck = Callable[[], Awaitable[bool]]


class Metrics:
    def __init__(self, service: str):
        self.service = service
        self.counters: dict[str, float] = defaultdict(float)
        self.latency_sum: dict[str, float] = defaultdict(float)
        self.latency_n: dict[str, int] = defaultdict(int)

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        self.counters[self._key(name, labels)] += value

    def observe(self, name: str, seconds: float, **labels: str) -> None:
        k = self._key(name, labels)
        self.latency_sum[k] += seconds
        self.latency_n[k] += 1

    @staticmethod
    def _key(name: str, labels: dict) -> str:
        if not labels:
            return name
        inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{inner}}}"

    def render(self) -> str:
        lines = [f"{k} {v}" for k, v in self.counters.items()]
        for k, s in self.latency_sum.items():
            base, _, rest = k.partition("{")
            lab = "{" + rest if rest else ""
            lines.append(f"{base}_seconds_sum{lab} {s}")
            lines.append(f"{base}_seconds_count{lab} {self.latency_n[k]}")
        return "\n".join(lines) + "\n"


def create_app(service: str, ready_check: Optional[ReadyCheck] = None) -> tuple[FastAPI, Metrics]:
    app = FastAPI(title=service)
    metrics = Metrics(service)

    @app.middleware("http")
    async def _timing(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        if request.url.path not in ("/health", "/ready", "/metrics"):
            metrics.inc("http_requests_total", path=request.url.path, status=str(response.status_code))
            metrics.observe("http_request", time.perf_counter() - t0, path=request.url.path)
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": service}

    @app.get("/ready")
    async def ready():
        ok = True if ready_check is None else await ready_check()
        if not ok:
            from fastapi import HTTPException
            raise HTTPException(503, "not ready")
        return {"status": "ready"}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics_endpoint():
        return metrics.render()

    return app, metrics
