"""Shared data formats (Guide Section 2). Every service imports these so that
all modules validate the same JSON. Change a schema here, in one place."""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

DIMENSIONS: tuple[str, ...] = (
    "demand_pain",
    "competition",
    "differentiation",
    "feasibility",
    "risk",
    "learning",
)
# The floor only applies to the first five dimensions (Description 5.3).
FLOOR_DIMENSIONS: tuple[str, ...] = DIMENSIONS[:5]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- 2.1
class IdeaCard(BaseModel):
    id: str
    name: str
    summary: str = ""
    problem: str = ""
    customer: str = ""
    niche_tags: list[str] = Field(default_factory=list)
    stage: str = "unknown"
    funding_usd: Optional[float] = None
    source: str  # hackernews | github | reddit | yc | producthunt
    url: str
    published_at: Optional[date] = None
    fetched_at: Optional[date] = None
    text: str = ""


Goal = Literal["startup", "portfolio", "course_project"]


class StudentProfile(BaseModel):
    user_id: str
    skills: list[str] = Field(default_factory=list)
    hours_per_week: float = Field(ge=0, le=80)
    weeks_available: int = Field(ge=1, le=104)
    team_size: int = Field(ge=1, le=10)
    compute: Literal["laptop", "free_gpu", "paid"] = "laptop"
    goal: Goal = "course_project"
    interests: list[str] = Field(default_factory=list)

    @property
    def available_hours(self) -> float:
        return self.hours_per_week * self.weeks_available * self.team_size


# ---------------------------------------------------------------- 2.2
class EvidenceItem(BaseModel):
    evidence_id: str  # "<card_id>#c<chunk>"
    card_id: str
    quote: str
    source: str
    url: str
    retrieved_at: str = Field(default_factory=now_iso)
    score: Optional[float] = None  # retrieval score


class DimensionScore(BaseModel):
    dimension: str
    score: float = Field(ge=0, le=5)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    rubric_version: str = ""
    model: str = ""
    abstained: bool = False

    @field_validator("dimension")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in DIMENSIONS:
            raise ValueError(f"unknown dimension {v}")
        return v


class ScorerOutput(BaseModel):
    """What the model (M10) must return. Validated; invalid -> retry -> fallback."""
    score: float = Field(ge=0, le=5)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    reason: str


# ---------------------------------------------------------------- 2.3
class Verdict(str, Enum):
    GO = "GO"
    PIVOT = "PIVOT"
    NO_GO = "NO-GO"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class GateInputs(BaseModel):
    """Facts the gates need, computed in code from the knowledge base (M6/M9)."""
    n_sources: int = 0           # independent sources (distinct cards/authors)
    n_platforms: int = 0         # distinct platforms (hackernews, reddit, ...)
    estimated_hours: float = 0   # build effort estimate for this idea
    blockers: list[str] = Field(default_factory=list)  # legal / safety blockers
    duplicate_of: Optional[str] = None  # existing product with same core features & user


class WhatIf(BaseModel):
    change: str
    dimension: Optional[str] = None
    from_score: Optional[float] = None
    to_score: Optional[float] = None
    new_score: Optional[float] = None
    new_verdict: str
    stable: bool = False


class VerdictResult(BaseModel):
    idea_id: str = ""
    version: int = 1
    run_id: str = ""
    verdict: Verdict
    stability: Literal["STABLE", "BORDERLINE"] = "STABLE"
    score: Optional[float] = None
    confidence: float = 0.0
    gates: dict[str, str]
    gate_messages: dict[str, str] = Field(default_factory=dict)
    weights: dict[str, float]
    thresholds: dict[str, float]
    scores: list[DimensionScore]
    weakest_dimension: Optional[str] = None
    reason: str = ""
    missing: list[str] = Field(default_factory=list)  # for INSUFFICIENT_EVIDENCE (U10)
    what_would_make_go: list[WhatIf] = Field(default_factory=list)
    sensitivity: dict[str, Any] = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)


class TraceRecord(BaseModel):
    run_id: str
    step_id: int
    parent_step: Optional[int] = None
    agent: str
    kind: Literal["tool_call", "llm_call", "decision"]
    tool: Optional[str] = None
    input: str = ""
    output: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    retries: int = 0
    model: Optional[str] = None
    cache_hit: bool = False
    error: Optional[str] = None
    ts: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------- critic
class Claim(BaseModel):
    claim_id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    dimension: Optional[str] = None


class ClaimCheck(BaseModel):
    claim_id: str
    supported: bool
    reason: str
    overlap: float = 0.0
