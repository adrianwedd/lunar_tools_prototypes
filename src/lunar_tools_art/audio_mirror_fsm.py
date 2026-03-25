"""Audio Mirror interaction state machine.

Pure logic FSM that drives the Audio Mirror art installation through
its interaction phases: detecting a viewer, capturing their voice,
deepening the conversation, delivering oracle insights, and departing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Valid states
IDLE = "IDLE"
DETECTION = "DETECTION"
FIRST_CAPTURE = "FIRST_CAPTURE"
DEEPENING = "DEEPENING"
ORACLE = "ORACLE"
DEPARTURE = "DEPARTURE"


@dataclass
class VoiceEntry:
    """A single captured voice segment."""

    sequence: int
    emotion: str
    duration_s: float
    confidence: float
    transcript: str


@dataclass
class SessionData:
    """Accumulated data for one viewer interaction session."""

    voice_entries: list[VoiceEntry] = field(default_factory=list)
    transcripts: list[dict] = field(default_factory=list)
    emotion_timeline: list[dict] = field(default_factory=list)
    interaction_count: int = 0
    start_time: float = field(default_factory=time.monotonic)


@dataclass
class FSMConfig:
    """Configuration for the Audio Mirror FSM."""

    max_detection_retries: int = 3
    min_deepening_exchanges: int = 3
    max_deepening_exchanges: int = 5
    face_lost_grace_s: float = 10.0
    speech_timeout_s: float = 30.0
    silence_timeout_s: float = 60.0
    max_interaction_s: float = 300.0
    min_reference_duration_s: float = 5.0


class AudioMirrorFSM:
    """State machine for the Audio Mirror art installation.

    Receives events and transitions between states:
    IDLE -> DETECTION -> FIRST_CAPTURE -> DEEPENING -> ORACLE -> DEPARTURE -> IDLE
    """

    def __init__(self, config: FSMConfig | None = None):
        self.config = config or FSMConfig()
        self.state: str = IDLE
        self.session: SessionData = SessionData()
        self._detection_retries: int = 0
        self._deepening_count: int = 0

    def on_face_detected(self) -> None:
        """Handle face detection event."""
        if self.state == IDLE:
            logger.info(f"Face detected, transitioning from {IDLE} to {DETECTION}")
            self.state = DETECTION
            self._detection_retries = 0
            self.session = SessionData()

    def on_face_lost(self) -> None:
        """Handle face lost event."""
        if self.state == DETECTION:
            logger.info(f"Face lost in {DETECTION}, returning to {IDLE}")
            self.state = IDLE
        elif self.state == FIRST_CAPTURE:
            logger.info(f"Face lost in {FIRST_CAPTURE}, transitioning to {DEPARTURE}")
            self.state = DEPARTURE
        elif self.state == DEEPENING:
            logger.info(f"Face lost in {DEEPENING}, transitioning to {DEPARTURE}")
            self.state = DEPARTURE
        elif self.state == ORACLE:
            logger.info(f"Face lost in {ORACLE}, transitioning to {DEPARTURE}")
            self.state = DEPARTURE

    def on_speech_captured(
        self,
        transcript: str,
        duration_s: float,
        confidence: float,
        emotion: str = "neutral",
    ) -> None:
        """Handle speech captured event."""
        entry = VoiceEntry(
            sequence=len(self.session.voice_entries) + 1,
            emotion=emotion,
            duration_s=duration_s,
            confidence=confidence,
            transcript=transcript,
        )
        self.session.voice_entries.append(entry)
        # Note: transcript with prosody is appended by the prototype, not the FSM,
        # to avoid duplication. The FSM only tracks voice_entries and emotion_timeline.
        self.session.emotion_timeline.append(
            {
                "timestamp": time.monotonic(),
                "primary": emotion,
                "intensity": confidence,
            }
        )
        self.session.interaction_count += 1

        if self.state == DETECTION:
            logger.info(
                f"Speech captured in {DETECTION}, transitioning to {FIRST_CAPTURE}"
            )
            self.state = FIRST_CAPTURE
        elif self.state == DEEPENING:
            self._deepening_count += 1
            logger.info(
                f"Speech captured in {DEEPENING}, "
                f"deepening count: {self._deepening_count}/{self.config.max_deepening_exchanges}"
            )
            if self._deepening_count >= self.config.max_deepening_exchanges:
                logger.info(f"Max exchanges reached, auto-transitioning to {ORACLE}")
                self.state = ORACLE

    def on_speech_timeout(self) -> None:
        """Handle speech timeout event."""
        if self.state == DETECTION:
            self._detection_retries += 1
            if self._detection_retries >= self.config.max_detection_retries:
                logger.info(
                    f"Speech timeout: retries {self._detection_retries} >= "
                    f"max {self.config.max_detection_retries}, returning to {IDLE}"
                )
                self.state = IDLE
            else:
                logger.info(
                    f"Speech timeout: retry {self._detection_retries}/{self.config.max_detection_retries}, "
                    f"staying in {DETECTION}"
                )

    def on_capture_complete(self) -> None:
        """Handle capture complete event."""
        if self.state == FIRST_CAPTURE:
            logger.info(
                f"Capture complete, transitioning from {FIRST_CAPTURE} to {DEEPENING}"
            )
            self.state = DEEPENING
            self._deepening_count = 0

    def on_stt_failure(self) -> None:
        """Handle STT failure event."""
        if self.state == FIRST_CAPTURE:
            logger.info(f"STT failure in {FIRST_CAPTURE}, returning to {DETECTION}")
            self.state = DETECTION

    def on_oracle_ready(self) -> None:
        """Handle oracle ready event."""
        if self.state == DEEPENING:
            logger.info(f"Oracle ready, transitioning from {DEEPENING} to {ORACLE}")
            self.state = ORACLE

    def on_insight_delivered(self) -> None:
        """Handle insight delivered event."""
        if self.state == ORACLE:
            logger.info(
                f"Insight delivered, transitioning from {ORACLE} to {DEPARTURE}"
            )
            self.state = DEPARTURE

    def on_cleanup_complete(self) -> None:
        """Handle cleanup complete event."""
        if self.state == DEPARTURE:
            logger.info(f"Cleanup complete, transitioning from {DEPARTURE} to {IDLE}")
            self.state = IDLE

    def on_silence_timeout(self) -> None:
        """Handle silence timeout event."""
        if self.state == DEEPENING:
            logger.info(f"Silence timeout in {DEEPENING}, transitioning to {DEPARTURE}")
            self.state = DEPARTURE

    @property
    def best_voice_quality(self) -> str:
        """Return voice quality based on total reference duration.

        Returns 'none', 'rough', 'developing', or 'good'.
        """
        if not self.session.voice_entries:
            return "none"
        total_duration = sum(e.duration_s for e in self.session.voice_entries)
        # Spec: >=15s = good, >=10s = developing, >=5s = rough
        if total_duration >= 3 * self.config.min_reference_duration_s:
            return "good"
        if total_duration >= 2 * self.config.min_reference_duration_s:
            return "developing"
        return "rough"

    @property
    def oracle_criteria_met(self) -> bool:
        """Return True if minimum exchanges met and voice quality >= developing."""
        return (
            self._deepening_count >= self.config.min_deepening_exchanges
            and self.best_voice_quality in ("developing", "good")
        )

    def reset(self) -> None:
        """Reset to IDLE with fresh session."""
        logger.info("Resetting FSM to IDLE")
        self.state = IDLE
        self.session = SessionData()
        self._detection_retries = 0
        self._deepening_count = 0
