from PIL import Image
import numpy as np
import time
from src.lunar_tools_art import Manager

class EvolvingCosmicMural:
    def __init__(self, lunar_tools_art_manager: Manager, midi_device_name="akai_lpd8", blend_speed=0.1):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.sdxl_lcm = self.lunar_tools_art_manager.sdxl_lcm
        self.renderer = self.lunar_tools_art_manager.renderer
        self.midi_input = self.lunar_tools_art_manager.midi_input
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.blend_speed = blend_speed

        if midi_device_name == "akai_lpd8":
            self.logger.warning("Using default MIDI device 'akai_lpd8'. Consider configuring a specific device name.")
        self.midi_input.device_name = midi_device_name # Configure device name
        self.base_prompt = "A vast cosmic scene with galaxies, nebulae, and stars"
        self.current_image = None
        self.modifiers = []
        self.last_generation_time = 0
        self.generation_interval = 10  # Generate a new image every 10 seconds
        self.midi_slider_states = [False] * 8 # To track if a slider has crossed the threshold

    def generate_cosmic_scene(self):
        prompt = self.base_prompt + ", " + ", ".join(self.modifiers)
        try:
            image, _ = self.sdxl_lcm.generate(prompt)
            return image
        except Exception as e:
            self.lunar_tools_art_manager.logger.error(f"Error generating image: {e}", exc_info=True)
            return None

    def blend_images(self, img1, img2, alpha):
        return Image.blend(img1, img2, alpha)

    def run(self):
        self.lunar_tools_art_manager.logger.info("Evolving Cosmic Mural: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed('q'):
                self.lunar_tools_art_manager.logger.info("Exiting Evolving Cosmic Mural.")
                break

            # Check MIDI inputs
            for i in range(8):
                slider_value = self.midi_input.get(f"A{i}", val_min=0, val_max=1)
                if slider_value > 0.5 and not self.midi_slider_states[i]:
                    self.modifiers.append([
                        "with a supernova explosion",
                        "featuring a black hole",
                        "with swirling cosmic dust",
                        "showing a planetary alignment",
                        "with a comet streaking across",
                        "featuring an alien space station",
                        "with aurora-like phenomenon",
                        "showing the birth of a new star"
                    ][i])
                    self.midi_slider_states[i] = True
                elif slider_value <= 0.5 and self.midi_slider_states[i]:
                    self.midi_slider_states[i] = False

            current_time = time.time()
            if current_time - self.last_generation_time > self.generation_interval:
                new_image = self.generate_cosmic_scene()
                self.last_generation_time = current_time
                self.modifiers = []  # Reset modifiers after generating new image

                if new_image is not None:
                    if self.current_image is not None:
                        # Blend the new image with the current image
                        for alpha in np.linspace(0, 1, 30):  # 30 frames for smooth transition
                            blended_image = self.blend_images(self.current_image, new_image, alpha)
                            try:
                                self.renderer.render(np.array(blended_image))
                            except Exception as e:
                                self.lunar_tools_art_manager.logger.error(f"Error rendering blended image: {e}", exc_info=True)
                            time.sleep(self.blend_speed)  # Adjust for desired transition speed
                    self.current_image = new_image
                else:
                    self.lunar_tools_art_manager.logger.info("Skipping image blending due to generation error.")

            # Render the current image
            if self.current_image is not None:
                try:
                    self.renderer.render(np.array(self.current_image))
                except Exception as e:
                    self.lunar_tools_art_manager.logger.error(f"Error rendering current image: {e}", exc_info=True)

            time.sleep(0.1)  # Small delay to prevent excessive CPU usage

if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    mural = EvolvingCosmicMural(lunar_tools_art_manager)
    mural.run()
