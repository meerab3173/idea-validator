"""Settings come from environment variables (ConfigMaps / Secrets on k8s).
Never hard-code localhost in an image: every URL has an env var."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


SERVICE_URLS = {
    "gateway": env("GATEWAY_URL", "http://gateway:8000"),
    "orchestrator": env("ORCHESTRATOR_URL", "http://orchestrator:8000"),
    "tools": env("TOOLS_URL", "http://tools:8000"),
    "kb": env("KB_URL", "http://kb:8000"),
    "analyst": env("ANALYST_URL", "http://analyst:8000"),
    "ideation": env("IDEATION_URL", "http://ideation:8000"),
    "validators": env("VALIDATORS_URL", "http://validators:8000"),
    "scorer": env("SCORER_URL", "http://scorer:8000"),
    "verdict": env("VERDICT_URL", "http://verdict:8000"),
    "critic": env("CRITIC_URL", "http://critic:8000"),
    "agentops": env("AGENTOPS_URL", "http://agentops:8000"),
}


@lru_cache
def load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def verdict_config_path() -> str:
    # In k8s the ConfigMap is mounted at /config/verdict.yaml
    p = env("VERDICT_CONFIG", "/config/verdict.yaml")
    if Path(p).exists():
        return p
    return str(Path(__file__).resolve().parents[3] / "config" / "verdict.yaml")


def rubrics_dir() -> Path:
    p = Path(env("RUBRICS_DIR", "/rubrics"))
    if p.exists():
        return p
    return Path(__file__).resolve().parents[3] / "rubrics"
