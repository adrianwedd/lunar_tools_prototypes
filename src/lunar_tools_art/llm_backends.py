# src/lunar_tools_art/llm_backends.py
"""Pluggable LLM backend abstraction.

Supports: Ollama (local), Ollama Cloud, Claude API, OpenRouter.
All backends implement .generate(prompt, system_prompt) -> str | None.
Selected via settings.toml [llm] section.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

log = logging.getLogger(__name__)


class LLMBackend(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None: ...


class OllamaLocalBackend(LLMBackend):
    def __init__(
        self, model: str = "llama3.1:8b", base_url: str = "http://localhost:11434"
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            data: dict = {"model": self.model, "prompt": prompt, "stream": False}
            if system_prompt:
                data["system"] = system_prompt
            resp = requests.post(
                f"{self.base_url}/api/generate", json=data, timeout=120
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            log.error(f"Ollama local generate failed: {e}")
            return None


def create_backend(config: dict) -> LLMBackend:
    """Create an LLM backend from a config dict (the [llm] section of settings.toml)."""
    provider = config.get("provider", "ollama")
    if provider == "ollama":
        ollama_cfg = config.get("ollama", {})
        return OllamaLocalBackend(
            model=ollama_cfg.get("model", "llama3.1:8b"),
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        )
    raise ValueError(f"Unknown LLM provider: {provider}")
