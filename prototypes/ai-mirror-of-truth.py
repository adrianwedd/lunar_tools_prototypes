"""AI Mirror of Truth - Interactive art installation.

An interactive art installation that observes humans through their emotions
and voice, reflecting their inner truth back to them through a mysterious
AI entity. Uses real face detection, voice prosody analysis, and cloned
voice synthesis.
"""

import json
import random
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from src.lunar_tools_art.prototype_base import PrototypeBase


class AiMirrorOfTruth(PrototypeBase):
    """AI Mirror of Truth prototype.

    Uses webcam emotion detection, voice prosody analysis, and LLM-driven
    entity generation to create an interactive mirror that reflects the
    viewer's emotional state.
    """

    def __init__(self, lunar_tools_art_manager, loop_delay=0.033, **kwargs):
        super().__init__(lunar_tools_art_manager, loop_delay=loop_delay, **kwargs)

        # Shortcuts for new infrastructure
        self.webcam = self.manager.webcam
        self.emotion_detector = self.manager.emotion_detector
        self.prosody_analyzer = self.manager.prosody_analyzer
        self.voice_client = self.manager.voice_client
        self.llm = self.manager.llm_backend

    def setup(self):
        """Initialize entity state, emotion buffer, and validate services."""
        self.conversation_history = []
        self.current_entity = None
        self.emotion_buffer = []
        self.emotion_trajectory = []
        self.last_entity_update = 0
        self.entity_update_interval = 15
        self.current_emotions = {
            "primary": "neutral",
            "intensity": 0.5,
            "secondary": "neutral",
        }
        self.visual_morph_state = 0.0

        # Validate Afterwords voice server
        try:
            health = self.voice_client.health()
            if health and health.get("status") == "ok":
                self.logger.info(
                    f"Afterwords server available, voices: {health.get('voices', [])}"
                )
            else:
                self.logger.warning(
                    "Afterwords server responded but status is not ok - "
                    "voice synthesis may be unavailable"
                )
        except Exception as e:
            self.logger.warning(
                f"Afterwords server unavailable: {e} - continuing without voice synthesis"
            )

        self.logger.info(
            "AI Mirror of Truth setup complete. Press SPACE to speak, q/esc to exit."
        )

    def update(self):
        """One iteration of the main loop."""
        current_time = time.time()

        # Get camera frame
        frame = None
        try:
            frame = self.webcam.get_img()
        except Exception as e:
            self.logger.error(f"Camera error: {e}")

        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Detect emotions using real emotion detector
        try:
            detections = self.emotion_detector.detect(frame)
            if detections:
                detection = detections[0]  # Use first face
                emotion_data = {
                    "primary": detection.get("primary", "neutral"),
                    "intensity": detection.get("intensity", 0.5),
                    "secondary": detection.get("secondary", "neutral"),
                    "face_detected": True,
                    "face_count": len(detections),
                }
                self.current_emotions = emotion_data
                self.emotion_buffer.append(emotion_data)

                # Track trajectory (last 10 primary emotions)
                self.emotion_trajectory.append(emotion_data["primary"])
                if len(self.emotion_trajectory) > 10:
                    self.emotion_trajectory.pop(0)
            else:
                self.emotion_buffer.append({"face_detected": False})
        except Exception as e:
            self.logger.error(f"Emotion detection error: {e}")

        # Keep buffer manageable
        if len(self.emotion_buffer) > 30:
            self.emotion_buffer.pop(0)

        # Check for voice input (SPACE key)
        if self.keyboard_input.is_key_pressed("space"):
            self._handle_voice_interaction(current_time)

        # Generate and render visual art
        visual_art = self._generate_visual_art(
            self.current_emotions, self.current_entity
        )
        self.renderer.render(visual_art)

    def cleanup(self):
        """Stop audio and log session end."""
        try:
            if hasattr(self.manager, "sound_player") and self.manager.sound_player:
                self.manager.sound_player.stop()
        except Exception as e:
            self.logger.error(f"Error stopping audio: {e}")

        self.logger.info(
            f"Mirror session ended after {len(self.conversation_history)} exchanges. "
            "Your truth remains..."
        )

    def _handle_voice_interaction(self, current_time):
        """Record audio, transcribe, analyze prosody, generate response, and speak."""
        self.logger.info("Listening for voice input...")

        # Record audio
        try:
            self.manager.audio_recorder.start_recording("temp_recording.wav")
            time.sleep(3)
            self.manager.audio_recorder.stop_recording()
        except Exception as e:
            self.logger.error(f"Recording error: {e}")
            return

        # Transcribe
        user_text = ""
        try:
            user_text = self.manager.speech2text.transcribe("temp_recording.wav")
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")

        if not user_text or not user_text.strip():
            return

        self.logger.info(f"User said: {user_text}")

        # Analyze prosody
        prosody_summary = "no prosody data"
        try:
            import librosa

            audio, sr = librosa.load("temp_recording.wav", sr=None)
            prosody_data = self.prosody_analyzer.analyze(audio, sr)
            prosody_summary = (
                f"pitch_mean={prosody_data.get('pitch_mean', 0):.0f}Hz, "
                f"energy={prosody_data.get('energy_mean', 0):.2f}, "
                f"speech_rate={prosody_data.get('speech_rate', 'unknown')}"
            )
        except Exception as e:
            self.logger.warning(f"Prosody analysis failed: {e}")

        # Generate or update entity if needed
        if (
            not self.current_entity
            or current_time - self.last_entity_update > self.entity_update_interval
        ):
            self.current_entity = self._generate_entity_personality()
            self.last_entity_update = current_time

            # Entity introduction on first interaction
            if len(self.conversation_history) == 0:
                intro = self.current_entity.get("greeting_message", "I see you...")
                self._speak(intro)
                self.conversation_history.append({"user": user_text, "entity": intro})

        # Generate entity response with adaptive system prompt
        entity_response = self._entity_respond(user_text, prosody_summary)
        self._speak(entity_response)

        self.conversation_history.append({"user": user_text, "entity": entity_response})
        self.logger.info(f"Entity: {entity_response}")

    def _generate_entity_personality(self):
        """Generate a unique AI entity based on current emotional state."""
        prompt = (
            "Create a unique AI entity personality based on the viewer's emotional state. "
            f"Recent emotions: {self.emotion_trajectory}. "
            "Generate a JSON response with: "
            '{"name": "entity_name", "personality_traits": ["trait1", "trait2"], '
            '"speaking_style": "description", "visual_characteristics": "description", '
            '"emotional_resonance": "how it connects", '
            '"greeting_message": "first message to viewer"}'
        )

        try:
            response = self.llm.generate(
                prompt,
                system_prompt="You generate JSON personality descriptions for AI art entities. Respond with valid JSON only.",
            )
            entity = json.loads(response)
            self.logger.info(f"Generated entity: {entity.get('name', 'Unknown')}")
            return entity
        except Exception as e:
            self.logger.error(f"Error generating entity: {e}")
            return {
                "name": "Echo",
                "personality_traits": ["reflective", "mysterious", "empathetic"],
                "speaking_style": "speaks in poetic fragments",
                "visual_characteristics": "shimmering, ethereal form",
                "emotional_resonance": "mirrors your hidden feelings",
                "greeting_message": "I see the truth in your eyes...",
            }

    def _entity_respond(self, user_input, prosody_summary):
        """Generate entity response using adaptive system prompt."""
        if not self.current_entity:
            return "I am still forming... speak to me again."

        entity_name = self.current_entity.get("name", "Echo")
        traits = ", ".join(
            self.current_entity.get("personality_traits", ["reflective"])
        )
        style = self.current_entity.get("speaking_style", "poetic")
        trajectory = (
            " -> ".join(self.emotion_trajectory[-5:])
            if self.emotion_trajectory
            else "unknown"
        )

        system_prompt = (
            f"You are a mysterious AI entity called {entity_name}. You observe humans through "
            "their emotions and voice, and you reflect their inner truth back to them.\n\n"
            f"Personality: {traits}\n"
            f"Speaking style: {style}\n\n"
            f"The viewer's emotion trajectory: {trajectory}\n"
            f"Their recent words and voice patterns: {prosody_summary}\n\n"
            "Respond as this entity -- empathetic, slightly otherworldly, reflecting their "
            "emotional state meaningfully. Keep responses under 50 words."
        )

        conversation_context = "\n".join(
            f"User: {conv['user']}\nEntity: {conv['entity']}"
            for conv in self.conversation_history[-3:]
        )

        prompt = f'Recent conversation:\n{conversation_context}\n\nUser just said: "{user_input}"'

        try:
            response = self.llm.generate(prompt, system_prompt=system_prompt)
            return response.strip()
        except Exception as e:
            self.logger.error(f"Error generating entity response: {e}")
            return "Your emotions ripple through me like waves... I feel what you feel."

    def _speak(self, text):
        """Synthesize and play speech via Afterwords voice client."""
        try:
            audio_data = self.voice_client.synthesize(text, voice="galadriel")
            if audio_data:
                # Write to temp file and play
                import subprocess  # nosec B404
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio_data)
                    temp_path = f.name
                try:
                    subprocess.run(  # nosec B603 B607
                        ["afplay", temp_path], check=False, timeout=30
                    )
                except Exception as e:
                    self.logger.warning(f"Audio playback failed: {e}")
            else:
                self.logger.warning(
                    f"Voice synthesis returned no audio for: {text[:50]}"
                )
        except Exception as e:
            self.logger.warning(f"Voice synthesis error: {e} - text was: {text[:50]}")

    def _generate_visual_art(self, emotion_data, entity_data):
        """Generate dynamic visual art based on emotional state."""
        width, height = 800, 600
        image = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(image)

        emotion_colors = {
            "joy": (255, 220, 100),
            "sadness": (100, 150, 255),
            "anger": (255, 100, 100),
            "fear": (150, 100, 150),
            "surprise": (255, 255, 100),
            "contempt": (150, 150, 100),
            "neutral": (150, 150, 150),
        }

        primary_color = emotion_colors.get(
            emotion_data.get("primary", "neutral"), (150, 150, 150)
        )
        intensity = emotion_data.get("intensity", 0.5)

        # Create swirling emotional patterns
        center_x, center_y = width // 2, height // 2
        num_spirals = int(intensity * 10) + 3

        for i in range(num_spirals):
            spiral_points = []
            for angle in range(0, 720, 10):
                radius = (angle / 720) * (intensity * 200) + 50
                x = center_x + radius * np.cos(np.radians(angle + i * 45))
                y = center_y + radius * np.sin(np.radians(angle + i * 45))
                spiral_points.append((x, y))

            for j in range(len(spiral_points) - 1):
                alpha = int(255 * (1 - j / len(spiral_points)))
                color = tuple(int(c * alpha / 255) for c in primary_color)
                draw.line([spiral_points[j], spiral_points[j + 1]], fill=color, width=3)

        # Add entity-specific visual elements
        if entity_data:
            for _ in range(5):
                x = random.randint(50, width - 50)
                y = random.randint(50, height - 50)
                size = random.randint(20, 60)
                orb_color = tuple(int(c * 0.7) for c in primary_color)
                draw.ellipse(
                    [x - size // 2, y - size // 2, x + size // 2, y + size // 2],
                    fill=orb_color,
                    outline=primary_color,
                    width=2,
                )

        image = image.filter(ImageFilter.GaussianBlur(radius=1))
        return np.array(image)
