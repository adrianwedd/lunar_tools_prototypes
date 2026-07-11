"""Text2Speech adapter over the Afterwords VoiceClient.

VoiceClient.synthesize returns raw wav bytes (or None on failure); this
adapter writes those bytes to a .wav file and returns the path, matching
the file-path-returning contract the rest of the codebase expects from
Text2Speech-shaped tools.
"""

import logging

from ..exceptions import InferenceError
from ..utils import create_secure_temp_file

logger = logging.getLogger(__name__)


class Text2Speech:
    """Adapts VoiceClient (bytes-returning) to a file-path-returning generate()."""

    def __init__(self, voice_client, default_voice: str = "galadriel", output_dir=None):
        self.voice_client = voice_client
        self.default_voice = default_voice
        self.output_dir = output_dir

    def generate(self, text: str, voice: str | None = None) -> str:
        voice = voice or self.default_voice
        try:
            audio_bytes = self.voice_client.synthesize(text, voice)
        except Exception as e:
            health = self._safe_health()
            raise InferenceError(
                f"Afterwords synthesis failed: {e} (health={health})"
            ) from e

        if audio_bytes is None:
            health = self._safe_health()
            raise InferenceError(
                f"Afterwords synthesis returned no audio (health={health})"
            )

        path = create_secure_temp_file(suffix=".wav", directory=self.output_dir)
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path

    def _safe_health(self):
        try:
            return self.voice_client.health()
        except Exception as e:
            logger.warning(f"Afterwords health check failed: {e}")
            return None
