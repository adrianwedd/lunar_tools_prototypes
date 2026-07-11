"""Single gate for all cloud egress decisions (LLM, image gen, TTS)."""

import logging

from .config import config as _default_config
from .exceptions import CloudDisabledError

logger = logging.getLogger(__name__)
_CLOUD_MODES = {"cloud-ok", "cloud-llm"}


def cloud_allowed(cfg=_default_config) -> bool:
    mode = cfg.get("privacy.mode", "local-only")
    if mode == "cloud-llm":
        logger.warning("privacy.mode='cloud-llm' is deprecated; use 'cloud-ok'")
    return mode in _CLOUD_MODES


def require_cloud(feature: str, cfg=_default_config) -> None:
    if not cloud_allowed(cfg):
        raise CloudDisabledError(
            f"{feature} requires cloud egress but privacy.mode is 'local-only'"
        )


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _is_local_url(url: str) -> bool:
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    return host in _LOCAL_HOSTS or host.startswith("127.") or host.endswith(".local")


def require_local_url(url: str, feature: str, cfg=_default_config) -> None:
    """Under local-only mode, reject backends configured with non-local URLs.

    Nominally-local backends (Ollama, Afterwords) take arbitrary URLs from
    config; without this check a remote base_url would silently send
    prompts/audio off-machine despite privacy.mode='local-only'.
    """
    if not cloud_allowed(cfg) and not _is_local_url(url):
        raise CloudDisabledError(
            f"{feature} URL {url!r} is not local but privacy.mode is 'local-only'"
        )
