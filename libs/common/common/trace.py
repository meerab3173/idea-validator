"""Tracing client. Every agent step, tool call and model call writes a
TraceRecord under one run id: JSON line to stdout (always) and POST to M13
(best effort, never breaks the caller)."""
from __future__ import annotations

import itertools
import json
import sys
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from .config import SERVICE_URLS
from .schemas import TraceRecord

_step = itertools.count(1)


def emit(rec: TraceRecord, post: bool = True) -> None:
    sys.stdout.write(json.dumps({"trace": rec.model_dump()}) + "\n")
    sys.stdout.flush()
    if not post:
        return
    try:
        import httpx
        httpx.post(f"{SERVICE_URLS['agentops']}/trace", json=rec.model_dump(), timeout=1.0)
    except Exception:
        pass  # tracing must never break the request


@contextmanager
def span(run_id: str, agent: str, kind: str, tool: Optional[str] = None,
         input: str = "", parent: Optional[int] = None, model: Optional[str] = None,
         post: bool = True) -> Iterator[dict]:
    """with span(run, "competition_scorer", "tool_call", tool="search_kb") as s:
           s["output"] = ...; s["tokens_in"] = ...
    """
    step = next(_step)
    data: dict = {"step_id": step, "output": "", "tokens_in": 0, "tokens_out": 0,
                  "cost_usd": 0.0, "retries": 0, "cache_hit": False, "error": None}
    t0 = time.perf_counter()
    try:
        yield data
    except Exception as e:  # record and re-raise
        data["error"] = repr(e)
        raise
    finally:
        emit(TraceRecord(
            run_id=run_id, step_id=step, parent_step=parent, agent=agent, kind=kind,
            tool=tool, input=input[:2000], output=str(data["output"])[:2000],
            tokens_in=data["tokens_in"], tokens_out=data["tokens_out"],
            cost_usd=data["cost_usd"], latency_ms=int((time.perf_counter() - t0) * 1000),
            retries=data["retries"], model=model, cache_hit=data["cache_hit"], error=data["error"],
        ), post=post)
