"""Speech-to-text: mlx-whisper (default) with an optional faster-whisper backend.

MLX / faster-whisper are imported lazily inside methods so importing this
module never touches those stacks, and so tests can monkeypatch
``sys.modules["mlx_whisper"]`` / ``sys.modules["faster_whisper"]`` before they
are imported here.
"""

import logging
import math

from ..config import config
from ..exceptions import ConfigurationError, InferenceError
from ..inference_gate import INFERENCE_LOCK

logger = logging.getLogger(__name__)


class Transcription(str):
    """A ``str`` (the transcript) carrying transcription metadata.

    Legacy consumers that treat the return value of ``transcribe()`` as a
    plain string (``.strip()``, string formatting, equality, etc.) keep
    working unmodified; new code can additionally read ``.confidence`` and
    ``.language``.
    """

    def __new__(cls, text: str, confidence: float = 0.0, language: str = ""):
        obj = super().__new__(cls, text)
        obj.text = str(text)
        obj.confidence = confidence
        obj.language = language
        return obj


def _confidence_from_segments(segments) -> float:
    """Clamped exp(mean(segment avg_logprob)) in (0, 1]."""
    logprobs = [s.get("avg_logprob", 0.0) for s in segments or []]
    if not logprobs:
        return 0.0
    mean_logprob = sum(logprobs) / len(logprobs)
    confidence = math.exp(mean_logprob)
    return max(0.0, min(1.0, confidence))


class Speech2Text:
    """Transcribes audio via a configurable local backend."""

    def __init__(self):
        self.backend = config.get("whisper.backend", "mlx-whisper")
        self.model = config.get("whisper.model", "base.en")
        self._recorder = None

    def transcribe(
        self, path_or_array=None, *, file_path=None, duration=None
    ) -> Transcription:
        if path_or_array is None and file_path is not None:
            path_or_array = file_path
        if path_or_array is None and duration is not None:
            path_or_array = self._record(duration)
        if path_or_array is None:
            raise ConfigurationError(
                "transcribe() needs an audio path/array, file_path=, or duration="
            )
        if self.backend == "mlx-whisper":
            return self._transcribe_mlx(path_or_array)
        if self.backend == "faster-whisper":
            return self._transcribe_faster_whisper(path_or_array)
        raise ConfigurationError(f"Unknown whisper.backend: {self.backend!r}")

    def _record(self, duration):
        """Record ``duration`` seconds via the resolved AudioRecorder."""
        if self._recorder is None:
            from . import resolve

            self._recorder = resolve("AudioRecorder")()
        return self._recorder.record(duration)

    def _transcribe_mlx(self, path_or_array) -> Transcription:
        try:
            import mlx_whisper
        except ImportError as e:
            raise InferenceError("mlx-whisper is not installed") from e

        repo = f"mlx-community/whisper-{self.model}-mlx"
        try:
            with INFERENCE_LOCK:
                result = mlx_whisper.transcribe(path_or_array, path_or_hf_repo=repo)
        except Exception as e:
            logger.warning(f"mlx-whisper transcription failed: {e}")
            raise InferenceError("mlx-whisper transcription failed") from e

        text = result.get("text", "").strip()
        language = result.get("language", "")
        confidence = _confidence_from_segments(result.get("segments"))
        return Transcription(text, confidence=confidence, language=language)

    def _transcribe_faster_whisper(self, path_or_array) -> Transcription:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise InferenceError("faster-whisper is not installed") from e

        try:
            with INFERENCE_LOCK:
                model = WhisperModel(self.model)
                segments_iter, info = model.transcribe(path_or_array)
                segments = list(segments_iter)
        except Exception as e:
            logger.warning(f"faster-whisper transcription failed: {e}")
            raise InferenceError("faster-whisper transcription failed") from e

        text = "".join(s.text for s in segments).strip()
        language = getattr(info, "language", "") or ""
        confidence = _confidence_from_segments(
            [{"avg_logprob": s.avg_logprob} for s in segments]
        )
        return Transcription(text, confidence=confidence, language=language)
