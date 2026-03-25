"""Audio Mirror — an installation that speaks back to you in your own voice.

Captures viewer's voice progressively, clones it via Afterwords TTS,
and delivers personal insights as an AI oracle using the viewer's own voice.
The cloned voice improves over the interaction, building an emotional palette.
"""

import os
import subprocess  # nosec B404
import tempfile
import time
import uuid

import cv2
import numpy as np
from PIL import Image, ImageFilter

from src.lunar_tools_art.audio_mirror_fsm import AudioMirrorFSM, FSMConfig
from src.lunar_tools_art.prototype_base import PrototypeBase

ORACLE_SYSTEM_PROMPT = """You are The Mirror — an oracle that speaks in the viewer's own voice.

You observe humans through their facial emotions, voice patterns, and words.
You reflect their inner truth back to them — not as a chatbot, but as a revelation.

Your role: observe, synthesize, reveal. Never be cruel. Never trivialize. Always be genuine.
Never claim to know what the viewer is "hiding" — instead, notice patterns they may not see.

When generating prompts for the viewer, ask questions that elicit emotional range:
- Questions about fear, love, loss, hope, identity
- Questions that invite vulnerability, not interrogation
- Match your tone to their emotional state

When delivering insights (the oracle moment):
- Synthesize everything observed: emotion trajectory, prosody patterns, word content
- Find patterns, contradictions, recurring themes
- Deliver something the viewer didn't know they were showing
- Be poetic but grounded — not vague mysticism

Current viewer data:
{viewer_data}

You are in phase: {phase}
"""

DEFAULT_PROMPTS = {
    "detection": [
        "Say your name.",
        "Hello. Speak to me.",
        "I see you. Tell me who you are.",
    ],
    "deepening": [
        "Tell me something you've never told anyone.",
        "What are you afraid of?",
        "Describe someone you miss.",
        "What would you say to yourself ten years ago?",
        "What do you love most about being alive?",
    ],
    "acknowledgment": [
        "I hear you...",
        "Let me think about that...",
        "Your voice is becoming clearer to me...",
    ],
}


class AudioMirror(PrototypeBase):
    """Audio Mirror installation — progressive voice cloning + AI oracle."""

    def __init__(self, lunar_tools_art_manager, **kwargs):
        super().__init__(lunar_tools_art_manager, loop_delay=0.033, **kwargs)
        self.session_id = uuid.uuid4().hex[:8]
        self.fsm = None
        self._prompt_index = 0
        self._last_face_time = 0.0
        self._last_speech_time = 0.0
        self._processing = False
        self._default_voice = "galadriel"
        self._playback_proc = None
        self._playback_tmp = None
        self._detection_entered_time = 0.0
        self._clone_voice_names: dict[int, str] = {}  # sequence → verified voice_name

    def setup(self):
        self.fsm = AudioMirrorFSM(
            FSMConfig(
                min_deepening_exchanges=3,
                max_deepening_exchanges=5,
            )
        )

        # Check Afterwords server
        health = (
            self.manager.voice_client.health() if self.manager.voice_client else None
        )
        if health and health.get("ready"):
            voices = health.get("voices", [])
            self.logger.info(f"Afterwords ready with {len(voices)} voices")
            if self._default_voice not in voices and voices:
                self._default_voice = voices[0]
        else:
            self.logger.warning(
                "Afterwords server not available — TTS will be disabled"
            )

        self.logger.info(f"Audio Mirror session {self.session_id} starting")

    def update(self):
        frame = None
        try:
            frame = self.manager.webcam.get_img() if self.manager.webcam else None
        except Exception as e:
            self.logger.error(f"Camera error: {e}")

        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Emotion detection
        emotions = []
        if self.manager.emotion_detector:
            try:
                emotions = self.manager.emotion_detector.detect(frame)
            except Exception:  # nosec B110
                pass

        current_time = time.time()

        # FSM event: face detection
        if self.fsm.state == "IDLE":
            if emotions:
                self.fsm.on_face_detected()
                self._last_face_time = current_time
                self._detection_entered_time = current_time
                self._speak(self._get_prompt("detection"), use_clone=False)
        elif emotions:
            self._last_face_time = current_time
            # Track emotion timeline
            for e in emotions:
                self.fsm.session.emotion_timeline.append(
                    {
                        "timestamp": current_time,
                        "primary": e.primary_emotion,
                        "intensity": e.confidence,
                    }
                )
                # Keep timeline bounded
                if len(self.fsm.session.emotion_timeline) > 100:
                    self.fsm.session.emotion_timeline.pop(0)
        else:
            # No face — check grace period
            if self.fsm.state not in ("IDLE", "DEPARTURE"):
                if (
                    current_time - self._last_face_time
                    > self.fsm.config.face_lost_grace_s
                ):
                    self.fsm.on_face_lost()

        # FSM event: speech timeout (use detection entry time, not face time)
        if self.fsm.state == "DETECTION":
            if (
                current_time - self._detection_entered_time
                > self.fsm.config.speech_timeout_s
            ):
                self.fsm.on_speech_timeout()
                if self.fsm.state == "DETECTION":
                    self._detection_entered_time = current_time  # reset for next retry
                    self._speak(self._get_prompt("detection"), use_clone=False)

        # FSM event: silence timeout in deepening
        if self.fsm.state == "DEEPENING":
            if (
                self._last_speech_time > 0
                and current_time - self._last_speech_time
                > self.fsm.config.silence_timeout_s
            ):
                self.fsm.on_silence_timeout()

        # Check for voice input (SPACE key)
        if self.fsm.state in ("DETECTION", "FIRST_CAPTURE", "DEEPENING"):
            if (
                self.manager.keyboard_input
                and self.manager.keyboard_input.is_key_pressed(32)
            ):
                self._capture_and_process_speech()

        # FSM: oracle phase
        if self.fsm.state == "ORACLE" and not self._processing:
            self._deliver_insight()

        # FSM: departure
        if self.fsm.state == "DEPARTURE":
            self._cleanup_session()
            self.fsm.on_cleanup_complete()

        # Render
        self._render_mirror(frame, emotions)

    def cleanup(self):
        if self.fsm and self.fsm.state != "IDLE":
            self._cleanup_session()
        self.logger.info(f"Audio Mirror session {self.session_id} ended")

    def _capture_and_process_speech(self):
        """Record, transcribe, analyze prosody, clone voice, update FSM."""
        self._last_speech_time = time.time()

        # Record 5 seconds of audio
        audio_file = f"/tmp/audio-mirror-{self.session_id}-capture.wav"  # nosec B108
        try:
            if self.manager.audio_recorder:
                self.manager.audio_recorder.start_recording(audio_file)
                time.sleep(5)
                self.manager.audio_recorder.stop_recording()
        except Exception as e:
            self.logger.error(f"Recording failed: {e}")
            self.fsm.on_stt_failure()
            return

        # Transcribe
        transcript = ""
        confidence = 0.0
        try:
            if self.manager.speech2text:
                transcript = self.manager.speech2text.transcribe(audio_file) or ""
                confidence = 0.8 if transcript.strip() else 0.0
        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")

        if not transcript.strip():
            self.fsm.on_stt_failure()
            return

        # Prosody analysis
        prosody_result = None
        try:
            import librosa

            audio_data, sr = librosa.load(audio_file, sr=None)
            if self.manager.prosody_analyzer:
                prosody_result = self.manager.prosody_analyzer.analyze(audio_data, sr)
        except Exception as e:
            self.logger.warning(f"Prosody analysis failed: {e}")

        emotion_tag = prosody_result.emotion_tag if prosody_result else "neutral"

        # Get audio duration
        duration_s = 5.0  # default to recording length
        try:
            import soundfile as sf

            data, sr = sf.read(audio_file)
            duration_s = len(data) / sr
        except Exception:  # nosec B110
            pass

        # Update FSM
        self.fsm.on_speech_captured(
            transcript, duration_s, confidence, emotion=emotion_tag
        )
        self.logger.info(
            f"Captured: '{transcript[:50]}...' ({duration_s:.1f}s, {emotion_tag})"
        )

        # Clone voice via Afterwords
        if duration_s >= self.fsm.config.min_reference_duration_s:
            try:
                with open(audio_file, "rb") as f:
                    audio_bytes = f.read()
                if self.manager.voice_client:
                    result = self.manager.voice_client.clone_voice(
                        audio=audio_bytes,
                        session_id=self.session_id,
                        emotion=emotion_tag,
                        transcript=transcript,
                    )
                    if result:
                        # Store the verified voice name from Afterwords
                        self._clone_voice_names[result.sequence] = result.voice_name
                        self.logger.info(
                            f"Voice cloned: {result.voice_name} ({result.quality})"
                        )
            except Exception as e:
                self.logger.warning(f"Voice cloning failed: {e}")

        # If in FIRST_CAPTURE, advance to DEEPENING
        if self.fsm.state == "FIRST_CAPTURE":
            self.fsm.on_capture_complete()

            # First uncanny moment — speak back in their voice (if available)
            clone_voice = self._best_clone_voice()
            if clone_voice:
                self._speak("I can hear you now...", use_clone=True)
            else:
                self._speak("I'm still learning your voice...", use_clone=False)

        # If in DEEPENING, prompt for more
        if self.fsm.state == "DEEPENING":
            if self.fsm.oracle_criteria_met:
                self.fsm.on_oracle_ready()
            else:
                # Ask a deepening question
                self._speak(self._get_prompt("deepening"), use_clone=False)

        # Store transcript with prosody
        self.fsm.session.transcripts.append(
            {
                "text": transcript,
                "emotion": emotion_tag,
                "confidence": confidence,
                "prosody": (
                    {
                        "pitch_mean": (
                            prosody_result.pitch_mean if prosody_result else 0
                        ),
                        "energy": prosody_result.energy_rms if prosody_result else 0,
                        "pace_wps": prosody_result.pace_wps if prosody_result else 0,
                    }
                    if prosody_result
                    else {}
                ),
            }
        )

    def _deliver_insight(self):
        """Generate and speak the oracle insight."""
        self._processing = True

        # Speak acknowledgment while processing
        self._speak(self._get_prompt("acknowledgment"), use_clone=False)

        # Build viewer data for LLM
        viewer_data = self._build_viewer_data()

        # Generate insight via LLM
        insight = None
        if self.manager.llm_backend:
            system = ORACLE_SYSTEM_PROMPT.format(
                viewer_data=viewer_data,
                phase="oracle",
            )
            prompt = (
                "Deliver your oracle insight to this viewer. Synthesize everything you've observed "
                "about their emotions, voice patterns, and words into one penetrating, genuine observation. "
                "Something they didn't know they were showing. Under 50 words. Be poetic but grounded."
            )
            try:
                insight = self.manager.llm_backend.generate(
                    prompt, system_prompt=system
                )
            except Exception as e:
                self.logger.error(f"LLM insight generation failed: {e}")

        if not insight:
            insight = "In your voice I hear something you haven't named yet. A quiet truth, waiting."

        self.logger.info(f"Oracle insight: {insight}")

        # Deliver in the best available cloned voice
        self._speak(insight, use_clone=True)

        self.fsm.on_insight_delivered()
        self._processing = False

    def _speak(self, text: str, use_clone: bool = False):
        """Synthesize and play speech via Afterwords."""
        if not self.manager.voice_client:
            self.logger.info(f"[TTS disabled] {text}")
            return

        voice = self._best_clone_voice() if use_clone else None
        if not voice:
            voice = self._default_voice

        try:
            wav_bytes = self.manager.voice_client.synthesize(text, voice=voice)
            if wav_bytes:
                # Write to temp file and play (non-blocking)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(wav_bytes)
                    tmp_path = f.name
                try:
                    # Non-blocking: fire and forget, cleanup on next call
                    self._cleanup_last_playback()
                    self._playback_proc = subprocess.Popen(
                        ["afplay", tmp_path]
                    )  # nosec B603 B607
                    self._playback_tmp = tmp_path
                except Exception:  # nosec B110
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
        except Exception as e:
            self.logger.warning(f"TTS failed: {e}")

    def _cleanup_last_playback(self):
        """Clean up previous non-blocking playback process and temp file."""
        if self._playback_proc is not None:
            self._playback_proc.poll()
            if self._playback_proc.returncode is not None:
                # Process finished — clean up
                if self._playback_tmp:
                    try:
                        os.unlink(self._playback_tmp)
                    except OSError:
                        pass
                    self._playback_tmp = None
                self._playback_proc = None

    def _best_clone_voice(self) -> str | None:
        """Get the best available cloned voice using verified Afterwords names."""
        if not self._clone_voice_names:
            return None
        # Find the entry with longest duration among those successfully cloned
        best_seq = None
        best_dur = 0.0
        for entry in self.fsm.session.voice_entries:
            if (
                entry.sequence in self._clone_voice_names
                and entry.duration_s > best_dur
            ):
                best_seq = entry.sequence
                best_dur = entry.duration_s
        if best_seq is not None:
            return self._clone_voice_names[best_seq]
        return None

    def _get_prompt(self, category: str) -> str:
        """Get the next prompt from a category, cycling through options."""
        prompts = DEFAULT_PROMPTS.get(category, ["Speak to me."])
        prompt = prompts[self._prompt_index % len(prompts)]
        self._prompt_index += 1
        return prompt

    def _build_viewer_data(self) -> str:
        """Build structured viewer data string for LLM context."""
        timeline = self.fsm.session.emotion_timeline[-10:]
        trajectory = (
            " -> ".join(e.get("primary", "?") for e in timeline)
            if timeline
            else "unknown"
        )

        transcripts = []
        for t in self.fsm.session.transcripts:
            prosody = t.get("prosody", {})
            transcripts.append(
                f'"{t["text"]}" (emotion: {t.get("emotion", "?")}, '
                f'energy: {prosody.get("energy", 0):.2f}, '
                f'pitch: {prosody.get("pitch_mean", 0):.0f}Hz)'
            )

        return (
            f"Emotion trajectory: {trajectory}\n"
            f"Voice palette quality: {self.fsm.best_voice_quality}\n"
            f"Interaction count: {self.fsm.session.interaction_count}\n"
            f"Transcripts with prosody:\n" + "\n".join(f"  - {t}" for t in transcripts)
        )

    def _cleanup_session(self):
        """Delete voice palette from Afterwords, clean up temp files."""
        if self.manager.voice_client:
            try:
                self.manager.voice_client.cleanup_session(self.session_id)
                self.logger.info(f"Session {self.session_id} voice palette cleaned up")
            except Exception as e:
                self.logger.warning(f"Session cleanup failed: {e}")

        # Clean up local temp files
        self._cleanup_last_playback()
        capture_file = f"/tmp/audio-mirror-{self.session_id}-capture.wav"  # nosec B108
        try:
            if os.path.exists(capture_file):
                os.unlink(capture_file)
        except OSError:
            pass

    def _render_mirror(self, frame, emotions):
        """Render camera mirror with overlays."""
        if self.manager.renderer is None:
            return

        # Mirror the frame (flip horizontally)
        display = (
            cv2.flip(frame, 1)
            if frame is not None
            else np.zeros((480, 640, 3), dtype=np.uint8)
        )

        # Add visual treatment based on state
        if self.fsm and self.fsm.state == "ORACLE" and self._processing:
            # Dreamlike effect during processing
            pil = Image.fromarray(display)
            pil = pil.filter(ImageFilter.GaussianBlur(radius=3))
            display = np.array(pil)

        # Add emotion indicator overlay
        if emotions:
            primary = emotions[0].primary_emotion
            color_map = {
                "joy": (0, 255, 200),
                "sadness": (255, 150, 100),
                "anger": (0, 0, 255),
                "fear": (200, 100, 200),
                "surprise": (0, 255, 255),
                "neutral": (200, 200, 200),
            }
            color = color_map.get(primary, (200, 200, 200))
            cv2.rectangle(display, (10, 10), (30, 30), color, -1)

        self.manager.renderer.render(display)


if __name__ == "__main__":
    from src.lunar_tools_art.manager import LunarToolsArtManager

    manager = LunarToolsArtManager()
    mirror = AudioMirror(manager)
    mirror.run()
