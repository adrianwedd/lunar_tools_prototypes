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
