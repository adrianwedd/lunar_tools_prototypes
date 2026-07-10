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
