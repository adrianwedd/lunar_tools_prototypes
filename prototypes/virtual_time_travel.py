import time

from src.lunar_tools_art import Manager


class TimeTravelExperience:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        midi_device_name="akai_lpd8",
        loop_delay=0.1,
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.text2speech = self.lunar_tools_art_manager.text2speech
        self.renderer = self.lunar_tools_art_manager.renderer
        self.midi_input = self.lunar_tools_art_manager.midi_input
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger

        if midi_device_name == "akai_lpd8":
            self.logger.warning(
                "Using default MIDI device 'akai_lpd8'. Consider configuring a specific device name."
            )
        self.midi_input.device_name = midi_device_name
        self.historical_eras = [
            "Ancient Egypt",
            "Roman Empire",
            "Medieval Europe",
            "Renaissance",
            "Industrial Revolution",
            "Roaring Twenties",
            "Space Age",
            "Cyberpunk Future",
        ]
        self.current_era_index = -1
        self.loop_delay = loop_delay

    def generate_historical_visual(self, era):
        prompt = f"A detailed, historically accurate visual representation of the {era} era. Focus on architecture, clothing, and atmosphere."
        try:
            image, _ = self.lunar_tools_art_manager.dalle3.generate(prompt)
            return image
        except Exception as e:
            self.logger.error(
                f"Error generating visual for era {era}: {e}", exc_info=True
            )
            return None  # Return a placeholder image on error

    def run(self):
        self.logger.info("Virtual Time Travel: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Virtual Time Travel.")
                break

            # Map MIDI input (e.g., a slider or knob) to an era index
            # Assuming MIDI control 'A0' for era selection, ranging from 0 to 1
            midi_value = self.midi_input.get(
                "A0", val_min=0, val_max=len(self.historical_eras) - 1
            )
            new_era_index = int(round(midi_value))

            if new_era_index != self.current_era_index:
                self.current_era_index = new_era_index
                era = self.historical_eras[self.current_era_index]
                narration = f"Welcome to the {era} era."
                self.logger.info(narration)
                self.text2speech.generate(narration)

                image = self.generate_historical_visual(era)
                self.renderer.render(image)

            time.sleep(self.loop_delay)  # Small delay to prevent busy-waiting


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    experience = TimeTravelExperience(lunar_tools_art_manager)
    experience.run()
