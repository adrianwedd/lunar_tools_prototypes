import time
from datetime import datetime

from src.lunar_tools_art import Manager


class TemporalArtGallery:
    def __init__(
        self, lunar_tools_art_manager: Manager, prompts=None, check_interval=60
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.flux = self.lunar_tools_art_manager.flux
        self.renderer = self.lunar_tools_art_manager.renderer
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.prompts = (
            prompts
            if prompts is not None
            else [
                "Abstract art representing dawn",
                "Impressionist painting of midday",
                "Surrealist artwork depicting dusk",
                "Minimalist night scene",
            ]
        )
        self.check_interval = check_interval

    def get_current_artwork_index(self):
        current_hour = datetime.now().hour
        return current_hour % len(self.prompts)  # Cycle through prompts based on hour

    def generate_artwork(self, prompt):
        try:
            image, _ = self.flux.generate(
                prompt,
                image_size="square_hd",
                num_inference_steps=4,
                seed=int(time.time()),
            )
            return image
        except Exception as e:
            self.logger.error(
                f"Error generating artwork for prompt '{prompt}': {e}", exc_info=True
            )
            return None

    def run(self):
        self.logger.info("Temporal Art Gallery: Press 'q' to quit.")
        last_index = -1
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Temporal Art Gallery.")
                break

            current_index = self.get_current_artwork_index()

            if current_index != last_index:
                prompt = self.prompts[current_index]
                self.logger.info(f"Generating new artwork: {prompt}")
                image = self.generate_artwork(prompt)
                if image is not None:
                    try:
                        self.renderer.render(image)
                        last_index = current_index
                    except Exception as e:
                        self.logger.error(f"Error rendering image: {e}", exc_info=True)
                else:
                    self.logger.info(
                        "Skipping rendering due to image generation error."
                    )

            time.sleep(self.check_interval)  # Check for updates every minute


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    gallery = TemporalArtGallery(lunar_tools_art_manager)
    gallery.run()
