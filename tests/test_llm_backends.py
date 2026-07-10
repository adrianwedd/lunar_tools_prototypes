# tests/test_llm_backends.py
import os
from unittest.mock import MagicMock, patch

import pytest
import toml

from src.lunar_tools_art.exceptions import CloudDisabledError
from src.lunar_tools_art.llm_backends import (
    ClaudeBackend,
    LLMBackend,
    MissingCredentialError,
    OllamaCloudBackend,
    OllamaLocalBackend,
    OpenRouterBackend,
    create_backend,
)


@pytest.fixture(autouse=True)
def _allow_cloud():
    """Most of these tests exercise cloud-backend wiring, not the privacy
    gate itself; allow cloud egress by default so they read as before.
    Privacy-gate-specific tests below override this explicitly."""
    with patch(
        "src.lunar_tools_art.llm_backends.privacy.cloud_allowed", return_value=True
    ):
        yield


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


def test_ollama_cloud_generate():
    with patch.dict(
        os.environ,
        {"OLLAMA_CLOUD_API_KEY": "test-key"},  # pragma: allowlist secret
    ):
        backend = OllamaCloudBackend(model="llama3.1:70b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Cloud response"}}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("hello")
        assert result == "Cloud response"


def test_openrouter_generate():
    with patch.dict(
        os.environ,
        {"OPENROUTER_API_KEY": "test-key"},  # pragma: allowlist secret
    ):
        backend = OpenRouterBackend(model="meta-llama/llama-3.1-8b-instruct:free")
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "Router response"}}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = backend.generate("hello")
        assert result == "Router response"


def test_create_backend_all_providers():
    providers = {
        "ollama": OllamaLocalBackend,
        "ollama-cloud": OllamaCloudBackend,
        "openrouter": OpenRouterBackend,
    }
    for provider_name, expected_class in providers.items():
        with patch.dict(
            os.environ,
            {
                "OLLAMA_CLOUD_API_KEY": "k",
                "OPENROUTER_API_KEY": "k",
            },  # pragma: allowlist secret
        ):
            config = {"provider": provider_name}
            backend = create_backend(config)
            assert isinstance(backend, expected_class), f"Failed for {provider_name}"


def test_create_backend_from_toml_config():
    """Verify create_backend works with the shape of config from settings.toml."""
    toml_str = """
[llm]
provider = "ollama"

[llm.ollama]
model = "llama3.1:8b"
base_url = "http://localhost:11434"

[llm.claude]
model = "claude-sonnet-4-20250514"
api_key_env = "ANTHROPIC_API_KEY"  # pragma: allowlist secret
"""
    config = toml.loads(toml_str)
    backend = create_backend(config["llm"])
    assert isinstance(backend, OllamaLocalBackend)
    assert backend.model == "llama3.1:8b"


def test_claude_raises_on_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ANTHROPIC_API_KEY", None)  # pragma: allowlist secret
        with pytest.raises(MissingCredentialError):
            ClaudeBackend()


def test_ollama_cloud_raises_on_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OLLAMA_CLOUD_API_KEY", None)  # pragma: allowlist secret
        with pytest.raises(MissingCredentialError):
            OllamaCloudBackend()


def test_openrouter_raises_on_missing_key():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("OPENROUTER_API_KEY", None)  # pragma: allowlist secret
        with pytest.raises(MissingCredentialError):
            OpenRouterBackend()


def test_manager_has_llm_backend():
    """Verify the Manager initializes an LLM backend from config."""
    from src.lunar_tools_art.manager import LunarToolsArtManager

    with patch("src.lunar_tools_art.manager.create_backend") as mock_create:
        mock_create.return_value = OllamaLocalBackend(model="test")
        manager = LunarToolsArtManager()
        assert hasattr(manager, "llm_backend")


def test_create_backend_claude_blocked_when_cloud_disallowed():
    with patch(
        "src.lunar_tools_art.llm_backends.privacy.cloud_allowed", return_value=False
    ):
        config = {
            "provider": "claude",
            "claude": {
                "model": "claude-sonnet-4-20250514",
                "api_key_env": "ANTHROPIC_API_KEY",  # pragma: allowlist secret
            },
        }
        with pytest.raises(CloudDisabledError):
            create_backend(config)


def test_create_backend_mlx(monkeypatch):
    import sys
    import types

    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.load = MagicMock(return_value=("model", "tokenizer"))
    fake_mlx_lm.generate = MagicMock(return_value="mlx response")
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)

    from src.lunar_tools_art.llm_backends import MLXLocalBackend

    config = {"provider": "mlx", "mlx": {"model": "m"}}
    backend = create_backend(config)
    assert isinstance(backend, MLXLocalBackend)
    assert backend.generate("hi") == "mlx response"
