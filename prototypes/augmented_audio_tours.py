
import time
import os
from PIL import Image
from src.lunar_tools_art import Manager

class AugmentedAudioTour:
    def __init__(self, lunar_tools_art_manager: Manager, section_audio_map=None, check_interval=1):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.webcam = self.lunar_tools_art_manager.webcam
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.current_section = None
        self.section_audio_map = section_audio_map if section_audio_map is not None else {
            "section_1": "section1_narration.mp3",
            "section_2": "section2_music.mp3"
        }
        self.check_interval = check_interval

    def detect_position(self, img):
        # Use GPT-4 Vision to detect position based on the image
        try:
            # Convert numpy array image to PIL Image for Dalle3
            pil_img = Image.fromarray(img)
            
            # Save the image to a temporary file for GPT-4 Vision
            temp_image_path = ".output/temp_webcam_frame.png"
            pil_img.save(temp_image_path)

            prompt = "Analyze this image and identify the current section or landmark. Respond concisely with the section name (e.g., 'section_1', 'section_2', 'entrance', 'exit'). If unsure, respond 'unknown'."
            response = self.lunar_tools_art_manager.gpt4.generate_vision(prompt, image_path=temp_image_path)
            
            # Clean up the temporary image file
            os.remove(temp_image_path)

            detected_section = response.strip().lower()
            self.logger.info(f"Detected position: {detected_section}")
            return detected_section
        except Exception as e:
            self.logger.error(f"Error detecting position: {e}", exc_info=True)
            return "unknown" # Return unknown on error

    def run(self):
        self.logger.info("Augmented Audio Tours: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed('q'):
                self.logger.info("Exiting Augmented Audio Tours.")
                break

            img = self.webcam.get_img()
            position = self.detect_position(img)
            
            if position and position != self.current_section:
                audio_file = self.section_audio_map.get(position)
                if audio_file:
                    self.sound_player.play_sound(audio_file)
                else:
                    self.logger.warning(f"No audio file configured for section: {position}")
                self.current_section = position
            
            time.sleep(self.check_interval)  # Check every second

if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    tour = AugmentedAudioTour(lunar_tools_art_manager)
    tour.run()
