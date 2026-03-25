# src/lunar_tools_art/voice_client.py
"""Client for the Afterwords TTS server.

Wraps /health, /synthesize, /clone, and /session endpoints.
Supports progressive voice palette with emotion-tagged clips.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


@dataclass
class CloneResult:
    voice_name: str
    emotion: str
    quality: str  # "rough" | "developing" | "good"
    transcript: str
    transcript_confidence: float
    duration_s: float
    sequence: int = 0


class VoiceClient:
    def __init__(
        self, server_url: str = "http://localhost:7860", timeout: float = 120.0
    ):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict | None:
        try:
            resp = httpx.get(f"{self.server_url}/health", timeout=5.0)
            return resp.json()
        except Exception as e:
            log.error(f"Afterwords health check failed: {e}")
            return None

    def list_voices(self) -> list[str]:
        health = self.health()
        if health:
            return health.get("voices", [])
        return []

    def synthesize(
        self, text: str, voice: str, emotion: str | None = None
    ) -> bytes | None:
        try:
            body: dict = {"text": text, "voice": voice}
            if emotion:
                body["emotion"] = emotion
            resp = httpx.post(
                f"{self.server_url}/synthesize",
                json=body,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.content
            log.error(f"Synthesize failed: {resp.status_code} {resp.text}")
            return None
        except Exception as e:
            log.error(f"Synthesize request failed: {e}")
            return None

    def clone_voice(
        self,
        audio: bytes,
        session_id: str,
        emotion: str,
        transcript: str | None = None,
    ) -> CloneResult | None:
        try:
            files = {"audio": ("recording.wav", audio, "audio/wav")}
            data: dict = {"session_id": session_id, "emotion": emotion}
            if transcript:
                data["transcript"] = transcript
            resp = httpx.post(
                f"{self.server_url}/clone",
                files=files,
                data=data,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                j = resp.json()
                return CloneResult(
                    voice_name=j["voice"],
                    emotion=j["emotion"],
                    quality=j["quality"],
                    transcript=transcript or "",
                    transcript_confidence=j.get("transcript_confidence", 0.0),
                    duration_s=j.get("duration_s", 0.0),
                    sequence=j.get("sequence", 0),
                )
            log.error(f"Clone failed: {resp.status_code} {resp.text}")
            return None
        except Exception as e:
            log.error(f"Clone request failed: {e}")
            return None

    def cleanup_session(self, session_id: str) -> None:
        try:
            httpx.delete(
                f"{self.server_url}/session/{session_id}",
                timeout=10.0,
            )
        except Exception as e:
            log.warning(f"Session cleanup failed: {e}")
