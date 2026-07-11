import os
import tempfile
import time
import uuid

from PIL import Image

from src.lunar_tools_art import Manager


class AugmentedAudioTour:
    def __init__(
        self, lunar_tools_art_manager: Manager, section_audio_map=None, check_interval=1
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.webcam = self.lunar_tools_art_manager.webcam
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.current_section = None
        self.section_audio_map = (
            section_audio_map
            if section_audio_map is not None
            else {
                "section_1": "section1_narration.mp3",
                "section_2": "section2_music.mp3",
            }
        )
        self.check_interval = check_interval
        self._vision_unavailable_logged = False

    def detect_position(self, img):
        backend = self.lunar_tools_art_manager.llm_backend
        if backend is None:
            if not self._vision_unavailable_logged:
                self.logger.warning(
                    "No LLM backend configured; position detection disabled, "
                    "reporting 'unknown'."
                )
                self._vision_unavailable_logged = True
            return "unknown"

        pil_img = Image.fromarray(img)
        temp_fd, temp_image_path = tempfile.mkstemp(
            suffix=".png", prefix=f"webcam_frame_{uuid.uuid4().hex[:8]}_"
        )
        os.close(temp_fd)
        pil_img.save(temp_image_path)

        prompt = (
            "Analyze this image and identify the current section or landmark. "
            "Respond concisely with the section name (e.g., 'section_1', "
            "'section_2', 'entrance', 'exit'). If unsure, respond 'unknown'."
        )
        try:
            response = backend.generate_vision(prompt, image_path=temp_image_path)
        except NotImplementedError:
            if not self._vision_unavailable_logged:
                self.logger.warning(
                    f"LLM backend {type(backend).__name__} has no vision support; "
                    "position detection degraded to 'unknown'."
                )
                self._vision_unavailable_logged = True
            return "unknown"
        finally:
            if os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                except OSError as e:
                    self.logger.warning(f"Failed to remove {temp_image_path}: {e}")

        if not response:
            self.logger.warning("Vision backend returned no response; 'unknown'.")
            return "unknown"

        detected_section = response.strip().lower()
        self.logger.info(f"Detected position: {detected_section}")
        return detected_section

    def run(self):
        self.logger.info("Augmented Audio Tours: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Augmented Audio Tours.")
                break

            img = self.webcam.get_img()
            position = self.detect_position(img)

            if position and position != self.current_section:
                audio_file = self.section_audio_map.get(position)
                if audio_file:
                    self.sound_player.play_sound(audio_file)
                else:
                    self.logger.warning(
                        f"No audio file configured for section: {position}"
                    )
                self.current_section = position

            time.sleep(self.check_interval)  # Check every second


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    tour = AugmentedAudioTour(lunar_tools_art_manager)
    tour.run()
