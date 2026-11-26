"""M10 HTTP API: POST /score. The fine-tuned model runs in the `model-server`
container (Ollama/llama.cpp with the merged GGUF, OpenAI-compatible API at
MODEL_URL). This service builds the prompt, validates, retries and falls back."""
from __future__ import annotations

import os
from typing import Optional

import httpx
from pydantic import BaseModel

from common.app import create_app
from common.llm import LLM
from common.prompts import load_rubric, rubric_id, scorer_system, scorer_user
from common.schemas import DimensionScore
from common.trace import span

from .core import score

MODEL_URL = os.environ.get("MODEL_URL", "http://model-server:11434/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "scorer-lora")
MODEL_TAG = os.environ.get("MODEL_TAG", "scorer-lora@v1")


async def ready() -> bool:
    try:
        return httpx.get(MODEL_URL.replace("/v1", "") + "/", timeout=2).status_code < 500
    except Exception:
        return os.environ.get("ALLOW_FALLBACK_ONLY", "false") == "true"


app, metrics = create_app("scorer", ready)
hosted = LLM()


def primary(system: str, user: str):
    r = httpx.post(f"{MODEL_URL}/chat/completions", timeout=60, json={
        "model": MODEL_NAME, "temperature": 0, "max_tokens": 300,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], d.get("usage", {})


def fallback(system: str, user: str):
    r = hosted.complete(system, user, max_tokens=300)
    return r.text, {"prompt_tokens": r.tokens_in, "completion_tokens": r.tokens_out, "cost": r.cost_usd}


class ScoreIn(BaseModel):
    run_id: str = "adhoc"
    dimension: str
    idea: str
    evidence: list[dict]
    profile: Optional[dict] = None
    features: Optional[dict] = None
    use: str = "auto"  # auto | finetuned | hosted | base  (used by the comparison script)


@app.post("/score")
def score_endpoint(b: ScoreIn) -> DimensionScore:
    rub = load_rubric(b.dimension)
    system, user = scorer_system(b.dimension), scorer_user(b.idea, b.profile, b.evidence, b.features)
    allowed = {e["evidence_id"] for e in b.evidence}
    with span(b.run_id, f"{b.dimension}_scorer", "llm_call", model=MODEL_TAG, input=user) as s:
        if b.use == "hosted":
            res = score(system, user, allowed, fallback, hosted.model, None, "")
        else:
            res = score(system, user, allowed, primary, MODEL_TAG, fallback, hosted.model)
        s["tokens_in"] = res.usage.get("prompt_tokens", 0)
        s["tokens_out"] = res.usage.get("completion_tokens", 0)
        s["cost_usd"] = res.usage.get("cost", 0.0)
        s["retries"] = res.attempts - 1
        s["output"] = res.output.model_dump_json() if res.output else f"ABSTAIN {res.errors}"
    if res.fallback:
        metrics.inc("scorer_fallbacks_total", dimension=b.dimension)
    if res.errors:
        metrics.inc("scorer_invalid_outputs_total", value=len(res.errors))
    if res.output is None:  # abstain: no evidence-backed score
        return DimensionScore(dimension=b.dimension, score=0, confidence=0, abstained=True,
                              reason="Scorer abstained: no evidence-backed score. " + "; ".join(res.errors)[:300],
                              rubric_version=rubric_id(rub), model=res.model, features=b.features or {})
    o = res.output
    return DimensionScore(dimension=b.dimension, score=o.score, confidence=o.confidence,
                          evidence_ids=o.evidence_ids, reason=o.reason, features=b.features or {},
                          rubric_version=rubric_id(rub), model=res.model)
