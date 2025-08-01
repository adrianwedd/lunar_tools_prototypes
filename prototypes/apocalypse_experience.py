import time

from src.lunar_tools_art import Manager


class ApocalypseExperience:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        ambient_sound_file="apocalypse_ambient.mp3",
        loop_delay=1,
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.renderer = self.lunar_tools_art_manager.renderer
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.ambient_sound_file = ambient_sound_file
        self.loop_delay = loop_delay

    def generate_apocalypse_visual(self):
        prompt = "A desolate, post-apocalyptic landscape with ruined buildings and a stormy sky. Style: realistic, grim, high detail."
        try:
            image, _ = self.lunar_tools_art_manager.dalle3.generate(prompt)
            return image
        except Exception as e:
            self.lunar_tools_art_manager.logger.error(
                f"Error generating apocalypse visual: {e}", exc_info=True
            )
            return None  # Return None or a default image on error

    def run(self):
        self.logger.info("Apocalypse Experience: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Apocalypse Experience.")
                break

            scene = self.keyboard_input.get("s", button_mode="toggle")
            if scene:
                self.sound_player.play_sound(self.ambient_sound_file)
                image = self.generate_apocalypse_visual()
                self.renderer.render(image)

            time.sleep(self.loop_delay)


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    experience = ApocalypseExperience(lunar_tools_art_manager)
    experience.run()
