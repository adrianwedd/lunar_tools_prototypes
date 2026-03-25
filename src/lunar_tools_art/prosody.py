# src/lunar_tools_art/prosody.py
"""Voice prosody analysis using librosa.

Pure signal processing — no ML models. Extracts pitch, energy, pace,
pauses, and spectral features from audio. Infers a coarse emotion tag
from prosody features.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import librosa
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class PauseEvent:
    at: float  # seconds
    duration: float  # seconds


@dataclass
class ProsodyResult:
    pitch_mean: float
    pitch_variance: float
    energy_rms: float
    pace_wps: float  # 0.0 if no transcript alignment
    pauses: list[PauseEvent] = field(default_factory=list)
    spectral_centroid: float = 0.0
    emotion_tag: str = "neutral"


class ProsodyAnalyzer:
    def analyze(self, audio: np.ndarray, sr: int) -> ProsodyResult:
        # Guard: empty or invalid audio
        if audio.size == 0 or sr <= 0:
            return ProsodyResult(
                pitch_mean=0.0, pitch_variance=0.0, energy_rms=0.0, pace_wps=0.0
            )

        # Ensure float32 mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)

        # Energy
        energy_rms = float(np.sqrt(np.mean(audio**2)))

        # Pitch (F0) via pyin — wrapped for robustness across numba/librosa versions
        pitch_mean = 0.0
        pitch_variance = 0.0
        try:
            f0, voiced_flag, _ = librosa.pyin(audio, fmin=80, fmax=600, sr=sr)
            voiced_f0 = (
                f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
            )
            if len(voiced_f0) > 0:
                pitch_mean = float(np.nanmean(voiced_f0))
                pitch_variance = float(np.nanstd(voiced_f0))
        except Exception as e:
            log.warning(f"Pitch extraction failed (degrading gracefully): {e}")

        # Spectral centroid
        try:
            cent = librosa.feature.spectral_centroid(y=audio, sr=sr)
            spectral_centroid = float(np.mean(cent)) if cent.size > 0 else 0.0
        except Exception as e:
            log.warning(f"Spectral centroid failed: {e}")
            spectral_centroid = 0.0

        # Pause detection (energy-based)
        frame_length = int(0.025 * sr)
        hop_length = int(0.010 * sr)
        rms_frames = librosa.feature.rms(
            y=audio, frame_length=frame_length, hop_length=hop_length
        )[0]
        silence_threshold = 0.02
        pauses: list[PauseEvent] = []
        in_pause = False
        pause_start = 0.0
        for i, rms_val in enumerate(rms_frames):
            t = i * hop_length / sr
            if rms_val < silence_threshold:
                if not in_pause:
                    in_pause = True
                    pause_start = t
            else:
                if in_pause:
                    dur = t - pause_start
                    if dur > 0.3:  # only count pauses > 300ms
                        pauses.append(PauseEvent(at=pause_start, duration=dur))
                    in_pause = False
        # Flush trailing pause (audio ends during silence)
        if in_pause:
            end_t = len(rms_frames) * hop_length / sr
            dur = end_t - pause_start
            if dur > 0.3:
                pauses.append(PauseEvent(at=pause_start, duration=dur))

        # Emotion tag from prosody heuristics
        emotion_tag = _infer_emotion(energy_rms, pitch_mean, pitch_variance)

        return ProsodyResult(
            pitch_mean=pitch_mean,
            pitch_variance=pitch_variance,
            energy_rms=energy_rms,
            pace_wps=0.0,
            pauses=pauses,
            spectral_centroid=spectral_centroid,
            emotion_tag=emotion_tag,
        )


def _infer_emotion(energy: float, pitch_mean: float, pitch_var: float) -> str:
    """Coarse emotion from prosody. Not a classifier — a heuristic."""
    if energy < 0.01:
        return "neutral"
    if energy > 0.4 and pitch_var > 30:
        return "agitated"
    if energy > 0.3 and pitch_mean > 250:
        return "excited"
    if energy < 0.15 and pitch_mean < 180:
        return "subdued"
    if pitch_var < 10 and energy < 0.25:
        return "calm"
    return "neutral"
