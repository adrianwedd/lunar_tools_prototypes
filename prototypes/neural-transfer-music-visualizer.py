import os
import tempfile
import time
import uuid

import librosa  # For actual beat detection
import numpy as np
from PIL import Image

from src.lunar_tools_art import Manager


class NeuralTransferMusicVisualizer:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        loop_delay=0.01,
        audio_track="your_music_track.mp3",
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.webcam = self.lunar_tools_art_manager.webcam  # For capturing frames
        self.renderer = self.lunar_tools_art_manager.renderer
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.audio_track = audio_track  # Replace with your audio file
        self.loop_delay = loop_delay

    def _detect_beat(self, audio_data_path):
        try:
            y, sr = librosa.load(audio_data_path)
            onset_env = librosa.onset.onset_detect(y=y, sr=sr)
            # For simplicity, we'll just check if there are any onsets in the current frame's audio
            # In a real-time scenario, you'd process a continuous audio stream.
            return len(onset_env) > 0
        except Exception as e:
            self.logger.error(f"Error during beat detection: {e}", exc_info=True)
            return False

    def _run_neural_style_transfer(self, frame):
        self.logger.info("Applying neural style transfer...")
        try:
            # Convert numpy array frame to PIL Image
            pil_frame = Image.fromarray(frame)

            # Save the frame to a secure temporary file for SDXL_TURBO
            temp_fd, temp_image_path = tempfile.mkstemp(
                suffix=".png", prefix=f"style_transfer_{uuid.uuid4().hex[:8]}_"
            )
            os.close(temp_fd)  # Close the file descriptor, keep the path
            pil_frame.save(temp_image_path)

            # Use SDXL_TURBO to generate a stylized image
            # For simplicity, we'll use a fixed style prompt. In a real app, this could be dynamic.
            style_prompt = "a vibrant, abstract, painterly style"
            stylized_image, _ = self.lunar_tools_art_manager.sdxl_turbo.generate(
                style_prompt, image_path=temp_image_path
            )

            # Clean up the temporary image file
            if os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                except OSError as e:
                    self.logger.warning(f"Failed to remove {temp_image_path}: {e}")

            return np.array(stylized_image)  # Convert back to numpy array
        except Exception as e:
            self.logger.error(f"Error during neural style transfer: {e}", exc_info=True)
            return frame  # Return original frame on error

    def run(self):
        self.logger.info("Neural Transfer Music Visualizer: Press 'q' to quit.")
        self.logger.info(f"Playing audio track: {self.audio_track}")
        self.sound_player.play_sound(self.audio_track, loop=True)  # Loop the music

        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Neural Transfer Music Visualizer.")
                self.sound_player.stop_sound()  # Stop the music
                break

            # Capture a frame (from webcam or generated background)
            frame = self.webcam.get_img()
            if frame is None:
                self.logger.warning(
                    "No frame captured from webcam. Using a black placeholder."
                )
                frame = np.zeros(
                    (self.renderer.height, self.renderer.width, 3), dtype=np.uint8
                )

            # Simulate audio data for beat detection (in a real scenario, this would be live audio stream)
            audio_data_path = (
                self.audio_track
            )  # Use the actual audio track for beat detection

            if self._detect_beat(audio_data_path):
                self.logger.info("Beat detected! Applying style transfer...")
                try:
                    stylized_frame = self._run_neural_style_transfer(frame)
                    self.renderer.render(stylized_frame)
                except Exception as e:
                    self.logger.error(
                        f"Error during style transfer or rendering: {e}", exc_info=True
                    )
            else:
                # Render original frame if no beat detected, or a subtly animated version
                self.renderer.render(frame)

            time.sleep(self.loop_delay)  # Small delay for continuous updates


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    visualizer = NeuralTransferMusicVisualizer(lunar_tools_art_manager)
    visualizer.run()
