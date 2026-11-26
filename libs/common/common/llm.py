"""Language-model client used by agents (M8, M9 fallback, M12).

* Hosted model through any OpenAI-compatible API (Groq, OpenRouter,
  Gemini's OpenAI endpoint, Ollama...). Set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.
* RECORD / REPLAY: with LLM_MODE=replay, answers come from a JSON file keyed by
  a hash of the prompt, so behaviour tests run fast, free and offline
  (Guide Section 7, "Behaviour tests").
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PRICE_PER_1K = {"in": float(os.environ.get("LLM_PRICE_IN", "0.0005")),
                "out": float(os.environ.get("LLM_PRICE_OUT", "0.0015"))}


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str
    cached: bool = False


def _key(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n---\n" + user).encode()).hexdigest()[:16]


class LLM:
    def __init__(self, model: Optional[str] = None, mode: Optional[str] = None,
                 cassette: Optional[str] = None):
        # In the cluster this is http://tools:8000/llm/v1 (all egress goes through M5).
        self.base_url = os.environ.get("LLM_BASE_URL", "http://tools:8000/llm/v1")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
        self.mode = mode or os.environ.get("LLM_MODE", "live")  # live | record | replay
        self.cassette = Path(cassette or os.environ.get("LLM_CASSETTE", "eval/cassettes/default.json"))
        self._tape: dict = {}
        if self.mode in ("replay", "record") and self.cassette.exists():
            self._tape = json.loads(self.cassette.read_text())

    def complete(self, system: str, user: str, temperature: float = 0.0,
                 max_tokens: int = 600, json_mode: bool = True) -> LLMResponse:
        k = _key(system, user)
        if self.mode == "replay":
            if k not in self._tape:
                raise KeyError(f"no recorded answer for prompt {k}")
            t = self._tape[k]
            return LLMResponse(t["text"], t["tokens_in"], t["tokens_out"], 0.0, self.model, True)

        import httpx
        body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=60,
                       headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage", {})
        ti, to = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        cost = ti / 1000 * PRICE_PER_1K["in"] + to / 1000 * PRICE_PER_1K["out"]
        text = data["choices"][0]["message"]["content"]
        if self.mode == "record":
            self._tape[k] = {"text": text, "tokens_in": ti, "tokens_out": to}
            self.cassette.parent.mkdir(parents=True, exist_ok=True)
            self.cassette.write_text(json.dumps(self._tape, indent=1))
        return LLMResponse(text, ti, to, cost, self.model)


def parse_json(text: str) -> dict:
    """Models sometimes wrap JSON in ``` fences; strip them."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    s, e = t.find("{"), t.rfind("}")
    return json.loads(t[s:e + 1])
