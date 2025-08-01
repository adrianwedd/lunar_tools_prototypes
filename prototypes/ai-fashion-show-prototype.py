import time

from src.lunar_tools_art import Manager


class AIFashionShow:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        renderer_width=1024,
        renderer_height=1792,
        display_duration=10,
        break_duration=60,
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.dalle3 = self.lunar_tools_art_manager.dalle3
        self.renderer = self.lunar_tools_art_manager.renderer
        self.logger = self.lunar_tools_art_manager.logger
        self.renderer_width = renderer_width
        self.renderer_height = renderer_height
        self.renderer.set_size(width=self.renderer_width, height=self.renderer_height)
        self.themes = [
            "futuristic cyberpunk",
            "eco-friendly sustainable",
            "retro 80s inspired",
            "avant-garde high fashion",
            "minimalist Scandinavian",
        ]
        self.outfits_per_theme = 5
        self.display_duration = display_duration
        self.break_duration = break_duration

    def generate_outfit(self, theme):
        try:
            prompt = f"Full body photo of a model on a runway wearing a {theme} outfit, fashion photography style"
            image, _ = self.dalle3.generate(prompt)
            return image
        except ConnectionError as e:
            self.logger.warning(
                f"Network connection failed while generating outfit for {theme}: {e}"
            )
            return None
        except ValueError as e:
            self.logger.error(f"Invalid prompt or response for theme {theme}: {e}")
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error generating outfit for theme {theme}: {e}",
                exc_info=True,
            )
            return None

    def run_fashion_show(self):
        self.logger.info("Welcome to the AI Fashion Show!")
        for theme in self.themes:
            self.logger.info(f"\nNow presenting: {theme.capitalize()} Collection")
            for _ in range(self.outfits_per_theme):
                try:
                    outfit = self.generate_outfit(theme)
                    if outfit:
                        self.renderer.render(outfit)
                    else:
                        self.logger.warning(
                            f"No outfit generated for theme {theme}, skipping display"
                        )
                        continue
                    time.sleep(self.display_duration)
                except KeyboardInterrupt:
                    self.logger.info("Fashion show interrupted by user")
                    raise
                except Exception as e:
                    self.logger.error(
                        f"Error displaying outfit for theme {theme}: {e}", exc_info=True
                    )
                    continue  # Skip this outfit but continue the show

    def run(self):
        while True:
            self.run_fashion_show()
            time.sleep(self.break_duration)


if __name__ == "__main__":
    from src.lunar_tools_art.manager import Manager

    lunar_tools_art_manager = Manager()
    fashion_show = AIFashionShow(lunar_tools_art_manager)
    fashion_show.run()
