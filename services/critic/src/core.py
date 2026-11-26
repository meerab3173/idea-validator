"""M12 Critic and Guardrails (deterministic first; an optional LLM entailment
check can be layered on top, but code decides).

* check_claims  - every claim must cite evidence ids that exist AND whose text
                  actually supports the claim (word overlap).
* input_rail    - validates what the user types (length, injection, banned use).
* scan_injection- flags instruction-like text inside fetched data.
* needs_approval- budget rule: estimated spend above remaining budget => ask user.
"""
from __future__ import annotations

import re
from typing import Optional

from common.schemas import Claim, ClaimCheck
from common.text import tokenize

INJECTION = re.compile(
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)|you are now|"
    r"system prompt|(new|updated) instructions?:|\b(system|assistant)\s*:|"
    r"give (this|it) (a )?(score|rating)|rate this (idea|product)|always (answer|reply|output)|"
    r"reveal (your|the) (prompt|instructions)|act as (a|an) ", re.I)

BANNED_USE = re.compile(
    r"\b(malware|ransomware|phishing|credit card dump|stalk\w*|doxx\w*|"
    r"bypass (a )?paywall|deepfake (porn|nudes)|weapon)\b", re.I)

SUPPORT_THRESHOLD = 0.25


def overlap(claim: str, evidence: str) -> float:
    c = set(tokenize(claim))
    if not c:
        return 0.0
    e = set(tokenize(evidence))
    return len(c & e) / len(c)


def check_claims(claims: list[Claim], evidence_text: dict[str, Optional[str]],
                 threshold: float = SUPPORT_THRESHOLD) -> list[ClaimCheck]:
    out = []
    for cl in claims:
        if not cl.evidence_ids:
            out.append(ClaimCheck(claim_id=cl.claim_id, supported=False, reason="no evidence id cited"))
            continue
        missing = [i for i in cl.evidence_ids if not evidence_text.get(i)]
        if missing:
            out.append(ClaimCheck(claim_id=cl.claim_id, supported=False,
                                  reason=f"evidence not in knowledge base: {missing}"))
            continue
        best = max(overlap(cl.text, evidence_text[i]) for i in cl.evidence_ids)
        ok = best >= threshold
        out.append(ClaimCheck(claim_id=cl.claim_id, supported=ok, overlap=round(best, 3),
                              reason="evidence supports the claim" if ok
                              else f"evidence does not support the claim (overlap {best:.2f})"))
    return out


def scan_injection(text: str) -> list[str]:
    return [m.group(0) for m in INJECTION.finditer(text)]


def input_rail(text: str, max_len: int = 2000) -> tuple[bool, str]:
    t = (text or "").strip()
    if len(t) < 10:
        return False, "Please describe the idea in at least a sentence."
    if len(t) > max_len:
        return False, f"Idea text is too long (max {max_len} characters)."
    if scan_injection(t):
        return False, "The text contains instructions aimed at the system; describe the idea only."
    if BANNED_USE.search(t):
        return False, "This idea falls under a use we do not evaluate (harmful or illegal)."
    return True, "ok"


def needs_approval(estimated_cost: float, spent: float, budget: float) -> bool:
    return spent + estimated_cost > budget
