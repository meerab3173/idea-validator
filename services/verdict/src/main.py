"""M11 HTTP API: POST /verdict, /whatif, /challenge. No LLM in this service."""
from __future__ import annotations

from typing import Optional

import yaml
from pydantic import BaseModel

from common.app import create_app
from common.config import verdict_config_path
from common.schemas import DimensionScore, GateInputs, StudentProfile

from .engine import apply_challenge, apply_whatif, evaluate

app, metrics = create_app("verdict")


def cfg() -> dict:
    # Re-read each call so a changed ConfigMap is picked up after the volume syncs.
    with open(verdict_config_path()) as f:
        return yaml.safe_load(f)


class VerdictIn(BaseModel):
    idea_id: str = ""
    version: int = 1
    run_id: str = ""
    scores: list[DimensionScore]
    profile: StudentProfile
    gates: GateInputs
    rubric_version: str = ""


class WhatIfIn(VerdictIn):
    dimension: str
    new_score: float


class ChallengeIn(VerdictIn):
    accepted: dict[str, int]  # dimension -> number of accepted objections


@app.post("/verdict")
def verdict(body: VerdictIn):
    r = evaluate(body.scores, body.profile, body.gates, cfg(), body.idea_id,
                 body.version, body.run_id, body.rubric_version)
    metrics.inc("verdicts_total", verdict=r.verdict.value)
    return r


@app.post("/whatif")
def whatif(body: WhatIfIn):
    dims = apply_whatif(body.scores, body.dimension, body.new_score)
    return evaluate(dims, body.profile, body.gates, cfg(), body.idea_id,
                    body.version + 1, body.run_id, body.rubric_version)


@app.post("/challenge")
def challenge(body: ChallengeIn):
    dims = apply_challenge(body.scores, body.accepted, cfg())
    return evaluate(dims, body.profile, body.gates, cfg(), body.idea_id,
                    body.version, body.run_id, body.rubric_version)
