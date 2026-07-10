# src/lunar_tools_art/llm_backends.py
"""Pluggable LLM backend abstraction.

Supports: Ollama (local), Ollama Cloud, Claude API, OpenRouter.
All backends implement .generate(prompt, system_prompt) -> str | None.
Selected via settings.toml [llm] section.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

import requests

from . import privacy
from .inference_gate import INFERENCE_LOCK

log = logging.getLogger(__name__)


LLM_TIMEOUT = 30  # seconds — keep short for real-time installations


class MissingCredentialError(ValueError):
    """Raised when a required API key is not set."""


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
                f"{self.base_url}/api/generate", json=data, timeout=LLM_TIMEOUT
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            log.error(f"Ollama local generate failed: {e}")
            return None


class ClaudeBackend(LLMBackend):
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key_env: str = "ANTHROPIC_API_KEY",
    ):
        privacy.require_cloud("claude")
        import anthropic

        self.model = model
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise MissingCredentialError(
                f"Claude requires {api_key_env} environment variable to be set"
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            kwargs: dict = {
                "model": self.model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            msg = self._client.messages.create(**kwargs)
            return msg.content[0].text
        except Exception as e:
            log.error(f"Claude generate failed: {e}")
            return None


class OllamaCloudBackend(LLMBackend):
    """Ollama Cloud — OpenAI-compatible chat API with generous free tier."""

    def __init__(
        self, model: str = "llama3.1:70b", api_key_env: str = "OLLAMA_CLOUD_API_KEY"
    ):
        privacy.require_cloud("ollama-cloud")
        self.model = model
        self.api_key = os.environ.get(api_key_env, "")
        if not self.api_key:
            raise MissingCredentialError(
                f"Ollama Cloud requires {api_key_env} environment variable to be set"
            )
        self.base_url = "https://api.ollama.com/v1"

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages},
                timeout=LLM_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.error(f"Ollama Cloud generate failed: {e}")
            return None


class OpenRouterBackend(LLMBackend):
    """OpenRouter — free-tier access to many models via OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "meta-llama/llama-3.1-8b-instruct:free",
        api_key_env: str = "OPENROUTER_API_KEY",
    ):
        privacy.require_cloud("openrouter")
        self.model = model
        self.api_key = os.environ.get(api_key_env, "")
        if not self.api_key:
            raise MissingCredentialError(
                f"OpenRouter requires {api_key_env} environment variable to be set"
            )
        self.base_url = "https://openrouter.ai/api/v1"

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages},
                timeout=LLM_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.error(f"OpenRouter generate failed: {e}")
            return None


class MLXLocalBackend(LLMBackend):
    """Local MLX-native LLM inference via mlx-lm. Model cached per-process."""

    _cache: dict = {}

    def __init__(self, model: str):
        self.model_name = model

    def _load(self):
        cached = MLXLocalBackend._cache.get(self.model_name)
        if cached is not None:
            return cached
        from mlx_lm import load

        with INFERENCE_LOCK:
            cached = MLXLocalBackend._cache.get(self.model_name)
            if cached is None:
                cached = load(self.model_name)
                MLXLocalBackend._cache[self.model_name] = cached
        return cached

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        try:
            from mlx_lm import generate

            model, tokenizer = self._load()
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            with INFERENCE_LOCK:
                return generate(model, tokenizer, prompt=full_prompt)
        except Exception as e:
            log.error(f"MLX local generate failed: {e}")
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
    if provider == "claude":
        claude_cfg = config.get("claude", {})
        return ClaudeBackend(
            model=claude_cfg.get("model", "claude-sonnet-4-20250514"),
            api_key_env=claude_cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
        )
    if provider == "ollama-cloud":
        cloud_cfg = config.get("ollama_cloud", {})
        return OllamaCloudBackend(
            model=cloud_cfg.get("model", "llama3.1:70b"),
            api_key_env=cloud_cfg.get("api_key_env", "OLLAMA_CLOUD_API_KEY"),
        )
    if provider == "openrouter":
        or_cfg = config.get("openrouter", {})
        return OpenRouterBackend(
            model=or_cfg.get("model", "meta-llama/llama-3.1-8b-instruct:free"),
            api_key_env=or_cfg.get("api_key_env", "OPENROUTER_API_KEY"),
        )
    if provider == "mlx":
        mlx_cfg = config.get("mlx", {})
        return MLXLocalBackend(
            model=mlx_cfg.get("model", "mlx-community/Llama-3.2-3B-Instruct-4bit")
        )
    raise ValueError(f"Unknown LLM provider: {provider}")
