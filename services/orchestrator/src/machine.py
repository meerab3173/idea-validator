"""M3 Orchestrator: Validate and Discover workflows as explicit, testable
state machines. Every transition is traced; budgets stop the run and ask the
user; retries and timeouts wrap every call; unchanged work comes from cache."""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Protocol


class S(str, Enum):
    INTAKE = "INTAKE"
    CLARIFY = "CLARIFY"                 # waiting for the user's answers
    EVIDENCE = "EVIDENCE"
    AWAIT_APPROVAL = "AWAIT_APPROVAL"   # waiting: deep search would exceed budget
    SCORING = "SCORING"
    VERDICT = "VERDICT"
    CHALLENGE = "CHALLENGE"
    STABILITY = "STABILITY"
    CARD = "CARD"
    DONE = "DONE"
    FAILED = "FAILED"
    # Discover
    NICHES = "NICHES"
    GENERATE = "GENERATE"
    VALIDATE_ALL = "VALIDATE_ALL"
    RESULT = "RESULT"


WAITING = {S.CLARIFY, S.AWAIT_APPROVAL}
TERMINAL = {S.DONE, S.FAILED}


class Clients(Protocol):
    def rail(self, text: str) -> dict: ...
    def kb_stats_for(self, run_id: str, idea: str) -> dict: ...      # {"n_sources", "n_platforms"}
    def scout(self, run_id: str, query: str) -> dict: ...
    def score_all(self, run_id: str, idea: str, profile: dict) -> dict: ...
    def verdict(self, payload: dict) -> dict: ...
    def challenge_verdict(self, payload: dict) -> dict: ...
    def skeptic(self, run_id: str, idea: str, evidence: list[dict]) -> list[dict]: ...
    def critic(self, run_id: str, claims: list[dict]) -> list[dict]: ...
    def niches(self, interest: str) -> list[dict]: ...
    def generate(self, run_id: str, profile: dict, niche: str, n: int) -> dict: ...
    def save(self, kind: str, payload: dict) -> None: ...


@dataclass
class Budget:
    max_cost_usd: float
    max_tokens: int
    max_pages: int
    max_steps: int
    cost: float = 0.0
    tokens: int = 0
    pages: int = 0
    steps: int = 0

    def would_exceed(self, cost: float = 0, pages: int = 0) -> bool:
        return self.cost + cost > self.max_cost_usd or self.pages + pages > self.max_pages

    def over(self) -> Optional[str]:
        if self.cost > self.max_cost_usd: return "cost"
        if self.tokens > self.max_tokens: return "tokens"
        if self.pages > self.max_pages: return "pages"
        if self.steps > self.max_steps: return "steps"
        return None


def h(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def with_retry(fn: Callable, retries: int = 2, timeout: float = 120, backoff: float = 0.5):
    """Retry with back-off; a call slower than `timeout` counts as a failure."""
    last = None
    for attempt in range(retries + 1):
        t0 = time.monotonic()
        try:
            out = fn()
            if time.monotonic() - t0 > timeout:
                raise TimeoutError("call exceeded timeout")
            return out
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last  # type: ignore[misc]


# ====================================================================== Validate
@dataclass
class ValidateRun:
    run_id: str
    idea: str
    profile: dict
    idea_id: str = ""
    version: int = 1
    state: S = S.INTAKE
    budget: Optional[Budget] = None
    questions: list[dict] = field(default_factory=list)
    answers: dict = field(default_factory=dict)
    approval: Optional[bool] = None
    evidence_stats: dict = field(default_factory=dict)
    scored: dict = field(default_factory=dict)
    verdict: dict = field(default_factory=dict)
    objections: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    error: str = ""


class ValidateMachine:
    def __init__(self, clients: Clients, cfg: dict, cache: dict, rubric_set: str = "r1",
                 on_event: Callable[[dict], None] = lambda e: None):
        self.c, self.cfg, self.cache, self.rubric_set = clients, cfg, cache, rubric_set
        self.on_event = on_event

    # ---------------------------------------------------------------- driver
    def new(self, idea: str, profile: dict, idea_id: str = "", version: int = 1,
            run_id: Optional[str] = None) -> ValidateRun:
        b = self.cfg["validate"]
        return ValidateRun(run_id or f"run_{uuid.uuid4().hex[:8]}", idea, profile,
                           idea_id or f"idea_{uuid.uuid4().hex[:6]}", version,
                           budget=Budget(b["max_cost_usd"], b["max_tokens"], b["max_pages"], b["max_steps"]))

    def run(self, r: ValidateRun) -> ValidateRun:
        while r.state not in WAITING | TERMINAL:
            prev = r.state
            r.budget.steps += 1
            try:
                r.state = getattr(self, f"_{r.state.value.lower()}")(r)
            except Exception as e:  # noqa: BLE001
                r.error, r.state = repr(e), S.FAILED
            self._event(r, {"type": "transition", "from": prev.value, "to": r.state.value,
                            "spend": round(r.budget.cost, 5), "steps": r.budget.steps})
            why = r.budget.over()
            if why and r.state not in TERMINAL:
                r.error = f"budget exceeded ({why}); stopped"
                r.state = S.FAILED
        return r

    def answer(self, r: ValidateRun, answers: dict) -> ValidateRun:
        assert r.state == S.CLARIFY
        r.answers.update(answers)
        extra = " ".join(f"{q['id']}: {answers.get(q['id'], '')}" for q in r.questions if answers.get(q["id"]))
        if extra:
            r.idea = f"{r.idea} ({extra})"
        r.state = S.EVIDENCE
        return self.run(r)

    def approve(self, r: ValidateRun, ok: bool) -> ValidateRun:
        assert r.state == S.AWAIT_APPROVAL
        r.approval = ok
        if ok:  # the user accepted the stated cost: extend the budget by exactly that
            ds = self.cfg["deep_search"]
            r.budget.max_cost_usd += ds["pages"] * ds["est_cost_per_page_usd"]
            r.budget.max_pages += ds["pages"]
        self._event(r, {"type": "approval", "approved": ok})
        r.state = S.EVIDENCE
        return self.run(r)

    def _event(self, r: ValidateRun, e: dict) -> None:
        e = {"run_id": r.run_id, "ts": time.time(), **e}
        r.events.append(e)
        self.on_event(e)

    # ---------------------------------------------------------------- steps
    def _intake(self, r: ValidateRun) -> S:
        rail = self.c.rail(r.idea)
        if not rail["ok"]:
            r.error = rail["message"]
            return S.FAILED
        r.questions = clarifying_questions(r.idea, r.profile, self.cfg.get("max_clarifying_questions", 2))
        return S.CLARIFY if r.questions and not r.answers else S.EVIDENCE

    def _evidence(self, r: ValidateRun) -> S:
        stats = self.c.kb_stats_for(r.run_id, r.idea)
        r.evidence_stats = stats
        thin = stats["n_sources"] < 3 or stats["n_platforms"] < 2
        if thin and r.approval is None:
            ds = self.cfg["deep_search"]
            est = ds["pages"] * ds["est_cost_per_page_usd"]
            if r.budget.would_exceed(cost=est, pages=ds["pages"]):
                self._event(r, {"type": "approval_needed", "estimated_cost_usd": est,
                                "pages": ds["pages"], "spent": round(r.budget.cost, 4),
                                "budget": r.budget.max_cost_usd})
                return S.AWAIT_APPROVAL
            r.approval = True
        if thin and r.approval:
            self._event(r, {"type": "tool_call", "agent": "scout", "tool": "scout_on_demand"})
            res = with_retry(lambda: self.c.scout(r.run_id, r.idea), retries=1)
            r.budget.pages += self.cfg["deep_search"]["pages"]
            r.budget.cost += self.cfg["deep_search"]["pages"] * self.cfg["deep_search"]["est_cost_per_page_usd"]
            if res.get("cards_added"):
                r.evidence_stats = self.c.kb_stats_for(r.run_id, r.idea)
        return S.SCORING

    def _scoring(self, r: ValidateRun) -> S:
        key = h("score", r.idea, r.profile, self.rubric_set)
        if key in self.cache:  # re-run only what changed
            r.scored = self.cache[key]
            self._event(r, {"type": "cache_hit", "what": "scores"})
            return S.VERDICT
        self._event(r, {"type": "agent", "agent": "validators", "status": "running 4 scorers in parallel"})
        r.scored = with_retry(lambda: self.c.score_all(r.run_id, r.idea, r.profile),
                              retries=self.cfg.get("retries", 2), timeout=self.cfg.get("timeout_s", 120))
        for s in r.scored["scores"]:
            self._event(r, {"type": "score", "dimension": s["dimension"], "score": s["score"],
                            "abstained": s.get("abstained", False)})
        spent = r.scored.get("spend", {})
        r.budget.cost += spent.get("cost_usd", 0.0)
        r.budget.tokens += spent.get("tokens", 0)
        self.cache[key] = r.scored
        return S.VERDICT

    def _payload(self, r: ValidateRun, scores: list[dict]) -> dict:
        return {"idea_id": r.idea_id, "version": r.version, "run_id": r.run_id, "scores": scores,
                "profile": r.profile, "gates": r.scored["gates"], "rubric_version": self.rubric_set}

    def _verdict(self, r: ValidateRun) -> S:
        r.verdict = self.c.verdict(self._payload(r, r.scored["scores"]))
        self._event(r, {"type": "decision", "agent": "verdict_engine", "verdict": r.verdict["verdict"],
                        "score": r.verdict.get("score")})
        if r.verdict["verdict"] == "INSUFFICIENT_EVIDENCE":
            return S.CARD  # nothing to challenge: we abstain
        return S.CHALLENGE

    def _challenge(self, r: ValidateRun) -> S:
        objs = self.c.skeptic(r.run_id, r.idea, r.scored.get("evidence", []))
        claims = [{"claim_id": str(i), "text": o["text"], "evidence_ids": o.get("evidence_ids", []),
                   "dimension": o.get("dimension")} for i, o in enumerate(objs)]
        checks = self.c.critic(r.run_id, claims) if claims else []
        accepted: dict[str, int] = {}
        for o, ck in zip(objs, checks):
            o["supported"] = ck["supported"]
            if ck["supported"] and o.get("dimension"):
                accepted[o["dimension"]] = accepted.get(o["dimension"], 0) + 1
        r.objections = objs
        self._event(r, {"type": "agent", "agent": "skeptic+critic", "objections": len(objs),
                        "accepted": accepted})
        if accepted:
            r.verdict = self.c.challenge_verdict({**self._payload(r, r.scored["scores"]), "accepted": accepted})
        return S.STABILITY

    def _stability(self, r: ValidateRun) -> S:
        # Sensitivity and what-would-make-GO are computed inside M11 (deterministic).
        self._event(r, {"type": "decision", "agent": "verdict_engine", "stability": r.verdict.get("stability"),
                        "flips": r.verdict.get("sensitivity", {}).get("flipped", 0)})
        return S.CARD

    def _card(self, r: ValidateRun) -> S:
        card = {**r.verdict, "objections": r.objections, "evidence": r.scored.get("evidence", []),
                "idea_text": r.idea, "spend_usd": round(r.budget.cost, 5),
                "gate_inputs": r.scored.get("gates", {}), "features": r.scored.get("features", {})}
        r.verdict = card
        self.c.save("verdict", {"run_id": r.run_id, "idea_id": r.idea_id, "version": r.version,
                                "user_id": r.profile.get("user_id"), "rubric_set": self.rubric_set,
                                "idea_text": r.idea, "card": card})
        return S.DONE


def clarifying_questions(idea: str, profile: dict, max_q: int = 2) -> list[dict]:
    """Only questions whose answer can change the result."""
    from_hours = profile.get("hours_per_week", 0) * profile.get("weeks_available", 0) * profile.get("team_size", 1)
    qs = []
    if not re.search(r"\b(for|students?|teachers?|developers?|users?|sellers?|owners?|teams?|people)\b", idea, re.I):
        qs.append({"id": "target_user", "question": "Who exactly is the user? (it changes which competitors count)",
                   "changes": ["competition", "duplicate gate"]})
    if len(idea.split()) < 12:
        qs.append({"id": "must_have", "question": "Which 2-3 features must version 1 have? (it changes the effort estimate)",
                   "changes": ["feasibility gate"]})
    if from_hours <= 0:
        qs.append({"id": "hours", "question": "How many hours per week can you give?", "changes": ["feasibility"]})
    return qs[:max_q]


# ====================================================================== Discover
ORDER = {"GO": 0, "PIVOT": 1, "INSUFFICIENT_EVIDENCE": 2, "NO-GO": 3}


def discover(clients: Clients, vm: ValidateMachine, profile: dict, niche: str, run_id: str,
             n_ideas: int = 5, on_event: Callable[[dict], None] = lambda e: None) -> dict:
    on_event({"run_id": run_id, "type": "transition", "to": "NICHES"})
    niches = clients.niches(niche)
    on_event({"run_id": run_id, "type": "transition", "to": "GENERATE", "niches": len(niches)})
    gen = clients.generate(run_id, profile, niche, n_ideas)
    on_event({"run_id": run_id, "type": "transition", "to": "VALIDATE_ALL", "survivors": len(gen["ideas"]),
              "dropped": len(gen["dropped"]), "rounds": gen["rounds"]})

    def one(i, idea):
        text = f"{idea['title']}: {idea['pitch']} (for {idea.get('target_user') or 'students'})"
        r = vm.new(text, profile, run_id=f"{run_id}_{i}")
        r.answers = {"auto": "discover"}       # no clarifying questions inside Discover
        r.approval = False                     # no deep search inside Discover unless approved
        return vm.run(r)

    with ThreadPoolExecutor(max_workers=3) as pool:
        runs = list(pool.map(lambda x: one(*x), enumerate(gen["ideas"])))
    ranked = sorted([r for r in runs if r.state == S.DONE],
                    key=lambda r: (ORDER.get(r.verdict["verdict"], 9), -(r.verdict.get("score") or 0)))
    result = [{"idea": r.idea, "idea_id": r.idea_id, "verdict": r.verdict["verdict"],
               "score": r.verdict.get("score"), "stability": r.verdict.get("stability"),
               "reason": r.verdict.get("reason"), "card": r.verdict} for r in ranked]
    on_event({"run_id": run_id, "type": "transition", "to": "RESULT", "ideas": len(result)})
    return {"ideas": result, "dropped": gen["dropped"], "rounds": gen["rounds"]}


# ====================================================================== record / replay
RECORDED_METHODS = ("rail", "kb_stats_for", "scout", "score_all", "skeptic", "critic", "niches", "generate")


class RecordingClients:
    """Wraps real clients and records every tool/model result of a run, so the
    run can be replayed later without any network or model (AgenticOps)."""

    def __init__(self, inner: Clients):
        self.inner, self.tape = inner, {m: [] for m in RECORDED_METHODS}

    def __getattr__(self, name):
        fn = getattr(self.inner, name)
        if name not in RECORDED_METHODS:
            return fn

        def wrapped(*a, **k):
            out = fn(*a, **k)
            self.tape[name].append(out)
            return out
        return wrapped


class ReplayClients:
    """Plays back a recorded tape. verdict/challenge go to the real (deterministic)
    engine, so a replay checks that the same inputs still give the same verdict."""

    def __init__(self, tape: dict, verdict_fn, challenge_fn):
        self.tape = {k: list(v) for k, v in tape.items()}
        self.verdict, self.challenge_verdict = verdict_fn, challenge_fn
        self.saved: list = []

    def _next(self, name):
        if not self.tape.get(name):
            raise KeyError(f"replay: no recorded result left for {name}")
        return self.tape[name].pop(0)

    def rail(self, text): return self._next("rail")
    def kb_stats_for(self, run_id, idea): return self._next("kb_stats_for")
    def scout(self, run_id, q): return self._next("scout")
    def score_all(self, run_id, idea, profile): return self._next("score_all")
    def skeptic(self, run_id, idea, ev): return self._next("skeptic")
    def critic(self, run_id, claims): return self._next("critic")
    def niches(self, interest): return self._next("niches")
    def generate(self, run_id, profile, niche, n): return self._next("generate")
    def save(self, kind, payload): self.saved.append((kind, payload))
