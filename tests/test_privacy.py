import pytest

from lunar_tools_art import privacy
from lunar_tools_art.exceptions import (
    CloudDisabledError,
    HardwareUnavailableError,
    InferenceError,
    LunarToolsArtError,
)


class FakeConfig:
    def __init__(self, mode):
        self._mode = mode

    def get(self, key, default=None):
        return self._mode if key == "privacy.mode" else default


def test_new_exceptions_subclass_base():
    for exc in (CloudDisabledError, HardwareUnavailableError, InferenceError):
        assert issubclass(exc, LunarToolsArtError)


def test_local_only_blocks_cloud():
    assert privacy.cloud_allowed(FakeConfig("local-only")) is False
    with pytest.raises(CloudDisabledError):
        privacy.require_cloud("dalle3", FakeConfig("local-only"))


def test_cloud_ok_allows():
    assert privacy.cloud_allowed(FakeConfig("cloud-ok")) is True


def test_cloud_llm_alias_allows_with_warning(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        assert privacy.cloud_allowed(FakeConfig("cloud-llm")) is True
    assert any("deprecated" in r.message for r in caplog.records)


class TestRequireLocalUrl:
    def test_local_urls_allowed_under_local_only(self):
        cfg = FakeConfig("local-only")
        for url in (
            "http://localhost:7860",
            "http://127.0.0.1:11434",
            "http://[::1]:7860",
            "http://myhost.local:7860",
        ):
            privacy.require_local_url(url, "test", cfg)  # must not raise

    def test_remote_url_blocked_under_local_only(self):
        with pytest.raises(CloudDisabledError):
            privacy.require_local_url(
                "https://remote-ollama.example", "test", FakeConfig("local-only")
            )

    def test_loopback_lookalike_hostname_blocked_under_local_only(self):
        cfg = FakeConfig("local-only")
        for url in (
            "http://127.0.0.1.evil.example:80",
            "http://127.evil.example",
        ):
            with pytest.raises(CloudDisabledError):
                privacy.require_local_url(url, "test", cfg)

    def test_loopback_ip_literals_allowed_under_local_only(self):
        privacy.require_local_url(
            "http://127.5.5.5:11434", "test", FakeConfig("local-only")
        )

    def test_remote_url_allowed_under_cloud_ok(self):
        privacy.require_local_url(
            "https://remote-ollama.example", "test", FakeConfig("cloud-ok")
        )

    # These import the target module *inside* the test and patch/raise via
    # its own `privacy` reference: test_packaging.py purges lunar_tools_art
    # from sys.modules mid-suite, so module-level imports here can go stale.

    def test_voice_client_rejects_remote_url_under_local_only(self, monkeypatch):
        import lunar_tools_art.voice_client as vc_mod

        monkeypatch.setattr(vc_mod.privacy, "cloud_allowed", lambda cfg=None: False)
        with pytest.raises(vc_mod.privacy.CloudDisabledError):
            vc_mod.VoiceClient(server_url="https://tts.example")

    def test_ollama_backend_rejects_remote_url_under_local_only(self, monkeypatch):
        from lunar_tools_art import llm_backends

        monkeypatch.setattr(
            llm_backends.privacy, "cloud_allowed", lambda cfg=None: False
        )
        with pytest.raises(llm_backends.privacy.CloudDisabledError):
            llm_backends.OllamaLocalBackend(base_url="https://remote.example")


def test_pii_filter_clears_args_after_formatting():
    import logging

    from lunar_tools_art.config import PIIFilter

    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "privacy %s", (False,), None
    )
    assert PIIFilter().filter(rec) is True
    assert rec.args == ()
    assert rec.getMessage() == "privacy False"
