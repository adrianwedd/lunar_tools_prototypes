"""Real sounddevice/soundfile-backed audio recorder and player.

Kept out of headless mode (see ``tools/headless.py`` for deterministic fakes
used under ``LUNAR_HEADLESS=1``). ``sounddevice`` is imported lazily inside
methods so importing this module never touches PortAudio, and so tests can
monkeypatch ``sys.modules["sounddevice"]`` before it is imported here.
"""

import logging
import os

from ..exceptions import HardwareUnavailableError
from ..utils import create_secure_temp_file

logger = logging.getLogger(__name__)

DEFAULT_SAMPLERATE = 16000  # Whisper-native
PLAYBACK_SAMPLERATE = 24000
MAX_RECORD_SECONDS = 60  # upper bound for start_recording()/stop_recording() takes


class AudioRecorder:
    """Records audio from the default input device to WAV files."""

    def __init__(self, output_dir=None, samplerate=DEFAULT_SAMPLERATE):
        self.output_dir = output_dir
        self.samplerate = samplerate
        self._degraded = False
        self._active_buffer = None
        self._active_path = None

    def _check_device(self):
        """Raise HardwareUnavailableError (once) if no input device exists.

        After the first failure, further calls warn-once and no-op (return
        True to signal "already degraded, don't proceed").
        """
        if self._degraded:
            logger.debug("AudioRecorder is degraded; skipping hardware call.")
            return True

        import sounddevice as sd

        devices = sd.query_devices()
        has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
        if not has_input:
            self._degraded = True
            logger.warning("No audio input device available; AudioRecorder degraded.")
            raise HardwareUnavailableError("No audio input device available")
        return False

    def _resolve_path(self, file_path=None):
        if file_path:
            directory = os.path.dirname(file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            return file_path
        return create_secure_temp_file(suffix=".wav", directory=self.output_dir)

    def record(self, duration: float):
        """Blocking record for ``duration`` seconds; returns the WAV path."""
        if self._degraded:
            logger.debug("AudioRecorder degraded; record() is a no-op.")
            return None

        try:
            self._check_device()
        except HardwareUnavailableError:
            raise

        import sounddevice as sd
        import soundfile as sf

        frames = max(int(duration * self.samplerate), 1)
        data = sd.rec(frames, samplerate=self.samplerate, channels=1)
        sd.wait()

        path = self._resolve_path()
        sf.write(path, data, self.samplerate)
        return path

    def start_recording(self, file_path: str) -> None:
        """Begin a non-blocking recording that ``stop_recording`` finalizes.

        Uses ``sd.rec()`` with a generous frame cap; the returned buffer is
        filled in the background by the audio driver and read out (whatever
        has been captured so far) when ``stop_recording`` is called.
        """
        if self._degraded:
            logger.debug("AudioRecorder degraded; start_recording() is a no-op.")
            return None

        try:
            self._check_device()
        except HardwareUnavailableError:
            raise

        import sounddevice as sd

        self._active_path = self._resolve_path(file_path)
        max_frames = int(MAX_RECORD_SECONDS * self.samplerate)
        self._active_buffer = sd.rec(max_frames, samplerate=self.samplerate, channels=1)

    def stop_recording(self) -> str:
        """Stop the active recording and write it to disk; returns the path."""
        if self._degraded or self._active_buffer is None:
            return None

        import sounddevice as sd
        import soundfile as sf

        if hasattr(sd, "stop"):
            sd.stop()

        path = self._active_path
        sf.write(path, self._active_buffer, self.samplerate)

        self._active_buffer = None
        self._active_path = None
        return path


class SoundPlayer:
    """Plays audio files or in-memory arrays through the default output device."""

    def __init__(self):
        self._degraded = False

    def play_audio(self, path_or_array, samplerate=PLAYBACK_SAMPLERATE, blocking=False):
        if self._degraded:
            logger.debug("SoundPlayer degraded; play_audio() is a no-op.")
            return None

        import sounddevice as sd

        if isinstance(path_or_array, str):
            import soundfile as sf

            data, samplerate = sf.read(path_or_array)
        else:
            data = path_or_array

        try:
            sd.play(data, samplerate=samplerate, blocking=blocking)
        except Exception as e:  # pragma: no cover - defensive, hw-specific
            self._degraded = True
            logger.warning(f"Audio playback unavailable; SoundPlayer degraded: {e}")
        return None

    # 8 prototypes call `play_sound` — kept as an alias with blocking=True default.
    def play_sound(self, path):
        return self.play_audio(path, blocking=True)
