import json  # For parsing GPT-4 response
import os
import random
import tempfile
import time
import uuid

import librosa
import numpy as np
from PIL import Image, ImageDraw

from src.lunar_tools_art import Manager


class AcousticFingerprintPainter:
    def __init__(self, lunar_tools_art_manager: Manager):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.audio_recorder = lunar_tools_art_manager.audio_recorder
        self.gpt4 = lunar_tools_art_manager.gpt4
        self.renderer = lunar_tools_art_manager.renderer
        self.keyboard_input = lunar_tools_art_manager.keyboard_input
        self.logger = lunar_tools_art_manager.logger
        self.canvas_image = Image.new(
            "RGB", (self.renderer.width, self.renderer.height), color=(0, 0, 0)
        )  # Black canvas

    def _record_audio_sample(self, duration=3):
        self.logger.info(f"Recording audio sample for {duration} seconds...")
        # Create secure temporary file
        temp_fd, file_path = tempfile.mkstemp(
            suffix=".wav", prefix=f"acoustic_sample_{uuid.uuid4().hex[:8]}_"
        )
        os.close(temp_fd)  # Close the file descriptor, keep the path

        self.audio_recorder.start_recording(file_path)
        # Assuming audio_recorder.stop_recording() is blocking until recording is complete.
        # If not, a wait_for_recording_completion method would be ideal here.
        self.audio_recorder.stop_recording()
        self.logger.info("Audio recording complete.")
        return file_path

    def _extract_audio_features(self, audio_file_path):
        self.logger.info(f"Extracting features from {audio_file_path}...")
        try:
            y, sr = librosa.load(audio_file_path)
            # Extract MFCCs (Mel-frequency cepstral coefficients)
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            # Extract spectral centroid
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

            # Flatten and combine features. You might want to process these more meaningfully.
            # For simplicity, we'll take the mean and standard deviation of each feature over time.
            feature_vector = np.concatenate(
                (
                    np.mean(mfccs, axis=1),
                    np.std(mfccs, axis=1),
                    np.array([np.mean(spectral_centroids)]),
                    np.array([np.std(spectral_centroids)]),
                )
            )

            # Clean up the temporary audio file
            if os.path.exists(audio_file_path):
                try:
                    os.remove(audio_file_path)
                except OSError as e:
                    self.logger.warning(f"Failed to remove {audio_file_path}: {e}")

            return feature_vector.tolist()  # Convert to list for JSON serialization
        except Exception as e:
            self.logger.error(
                f"Error during audio feature extraction: {e}", exc_info=True
            )
            return [0.0] * (
                13 * 2 + 2
            )  # Return a default vector on error (13 MFCCs * 2 (mean/std) + 2 (centroid mean/std))

    def _get_stroke_parameters_from_gpt4(self, feature_vector):
        prompt = (
            f"Given the following audio feature vector: {feature_vector}. "
            "Return JSON describing abstract brushstroke parameters (length, curvature, color in RGB, start_x, start_y). "
            "Example: {{'length': 100, 'curvature': 0.5, 'color': [255, 0, 0], 'start_x': 100, 'start_y': 200}}"
        )
        self.logger.info("Requesting stroke parameters from GPT-4...")
        try:
            response = self.gpt4.generate(prompt)
            # Attempt to parse JSON, handle potential errors
            stroke_params = json.loads(response)
            return stroke_params
        except json.JSONDecodeError as e:
            self.logger.error(
                f"Error decoding JSON from GPT-4 response: {e}", exc_info=True
            )
            self.logger.error(f"GPT-4 response: {response}")
            return None
        except Exception as e:
            self.logger.error(
                f"Error getting stroke parameters from GPT-4: {e}", exc_info=True
            )
            return None

    def _draw_stroke(self, stroke_params):
        if not stroke_params:
            return

        length = stroke_params.get("length", 50)
        curvature = stroke_params.get("curvature", 0.1)
        color = tuple(stroke_params.get("color", [255, 255, 255]))
        start_x = stroke_params.get("start_x", random.randint(0, self.renderer.width))
        start_y = stroke_params.get("start_y", random.randint(0, self.renderer.height))

        draw = ImageDraw.Draw(self.canvas_image)

        # Enhanced procedural drawing with more variations
        num_segments = random.randint(5, 20)  # More segments for complex strokes
        segment_length = length / num_segments

        current_x, current_y = start_x, start_y

        for i in range(num_segments):
            angle = i * curvature + random.uniform(-0.5, 0.5)  # Add randomness to angle
            next_x = current_x + int(segment_length * np.cos(angle))
            next_y = current_y + int(segment_length * np.sin(angle))

            # Vary line width and color slightly
            line_width = random.randint(1, 8)
            line_color = (
                color[0] + random.randint(-20, 20),
                color[1] + random.randint(-20, 20),
                color[2] + random.randint(-20, 20),
            )
            line_color = tuple(max(0, min(255, c)) for c in line_color)  # Clamp colors

            draw.line(
                [(current_x, current_y), (next_x, next_y)],
                fill=line_color,
                width=line_width,
            )

            # Add a small ellipse at segment end for a textured look
            draw.ellipse(
                [
                    next_x - line_width / 2,
                    next_y - line_width / 2,
                    next_x + line_width / 2,
                    next_y + line_width / 2,
                ],
                fill=line_color,
            )

            current_x, current_y = next_x, next_y

    def run(self):
        self.logger.info(
            "Acoustic Fingerprint Painter: Press 'q' to quit. Press 'r' to record audio and paint."
        )
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Acoustic Fingerprint Painter.")
                break

            if self.keyboard_input.is_key_pressed("r"):
                audio_file = self._record_audio_sample()
                feature_vector = self._extract_audio_features(audio_file)
                stroke_params = self._get_stroke_parameters_from_gpt4(feature_vector)
                self._draw_stroke(stroke_params)
                self.renderer.render(np.array(self.canvas_image))

            time.sleep(0.1)  # Small delay to prevent busy-waiting


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    painter = AcousticFingerprintPainter(lunar_tools_art_manager)
    painter.run()
