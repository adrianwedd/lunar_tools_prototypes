# tests/test_llm_backends.py
import os
from unittest.mock import MagicMock, patch

import pytest

from src.lunar_tools_art.llm_backends import (
    ClaudeBackend,
    LLMBackend,
    OllamaLocalBackend,
    create_backend,
)


def test_llm_backend_is_abstract():
    with pytest.raises(TypeError):
        LLMBackend()


def test_ollama_local_generate():
    backend = OllamaLocalBackend(model="llama3.1:8b", base_url="http://localhost:11434")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"response": "Hello world"},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("Say hello")
        assert result == "Hello world"
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["prompt"] == "Say hello"
        assert call_json["model"] == "llama3.1:8b"


def test_ollama_local_generate_with_system_prompt():
    backend = OllamaLocalBackend(model="llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"response": "I am an oracle."},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("Who are you?", system_prompt="You are an oracle.")
        assert result == "I am an oracle."
        call_json = mock_post.call_args[1]["json"]
        assert call_json["system"] == "You are an oracle."


def test_ollama_local_returns_none_on_error():
    backend = OllamaLocalBackend(model="llama3.1:8b")
    with patch("requests.post", side_effect=Exception("Connection refused")):
        result = backend.generate("hello")
        assert result is None


def test_create_backend_ollama():
    config = {
        "provider": "ollama",
        "ollama": {"model": "llama3.1:8b", "base_url": "http://localhost:11434"},
    }
    backend = create_backend(config)
    assert isinstance(backend, OllamaLocalBackend)


def test_claude_generate():
    with patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key"},  # pragma: allowlist secret
    ):
        backend = ClaudeBackend(model="claude-sonnet-4-20250514")
    with patch.object(backend, "_client") as mock_client:
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Insight delivered.")]
        mock_client.messages.create.return_value = mock_msg
        result = backend.generate("Analyze this", system_prompt="You are an oracle")
        assert result == "Insight delivered."


def test_claude_returns_none_on_error():
    with patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key"},  # pragma: allowlist secret
    ):
        backend = ClaudeBackend(model="claude-sonnet-4-20250514")
    backend._client.messages.create = MagicMock(side_effect=Exception("API error"))
    result = backend.generate("hello")
    assert result is None


def test_create_backend_claude():
    with patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key"},  # pragma: allowlist secret
    ):
        config = {
            "provider": "claude",
            "claude": {
                "model": "claude-sonnet-4-20250514",
                "api_key_env": "ANTHROPIC_API_KEY",  # pragma: allowlist secret
            },
        }
        backend = create_backend(config)
        assert isinstance(backend, ClaudeBackend)
