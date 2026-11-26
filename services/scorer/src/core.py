"""M10 scoring logic: call fine-tuned model -> validate JSON + evidence ids ->
retry once -> fall back to hosted model -> log the fallback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from pydantic import ValidationError

from common.llm import parse_json
from common.schemas import ScorerOutput

Complete = Callable[[str, str], tuple[str, dict]]  # (system, user) -> (text, usage)


class InvalidOutput(Exception):
    pass


def validate(text: str, allowed_ids: set[str]) -> Optional[ScorerOutput]:
    """Returns None for an abstain. Raises InvalidOutput otherwise."""
    try:
        data = parse_json(text)
    except Exception as e:  # noqa: BLE001
        raise InvalidOutput(f"not JSON: {e}")
    if data.get("abstain") is True:
        return None
    try:
        out = ScorerOutput(**data)
    except ValidationError as e:
        raise InvalidOutput(f"schema: {e.errors()[:1]}")
    if not out.evidence_ids:
        raise InvalidOutput("no evidence ids")
    fake = [i for i in out.evidence_ids if i not in allowed_ids]
    if fake:
        raise InvalidOutput(f"invented evidence ids: {fake}")
    return out


@dataclass
class ScoreResult:
    output: Optional[ScorerOutput]
    model: str
    attempts: int
    fallback: bool
    errors: list[str]
    usage: dict


def score(system: str, user: str, allowed_ids: set[str], primary: Complete, primary_name: str,
          fallback: Optional[Complete], fallback_name: str) -> ScoreResult:
    errors: list[str] = []
    usage: dict = {}
    for attempt in (1, 2):  # try once, retry once
        try:
            text, usage = primary(system, user)
            return ScoreResult(validate(text, allowed_ids), primary_name, attempt, False, errors, usage)
        except InvalidOutput as e:
            errors.append(f"{primary_name} attempt {attempt}: {e}")
        except Exception as e:  # noqa: BLE001 - model server down / timeout
            errors.append(f"{primary_name} attempt {attempt}: {e!r}")
    if fallback is None:
        return ScoreResult(None, primary_name, 2, False, errors, usage)
    try:
        text, usage = fallback(system, user)
        return ScoreResult(validate(text, allowed_ids), fallback_name, 3, True, errors, usage)
    except Exception as e:  # noqa: BLE001
        errors.append(f"{fallback_name}: {e!r}")
        return ScoreResult(None, fallback_name, 3, True, errors, usage)
