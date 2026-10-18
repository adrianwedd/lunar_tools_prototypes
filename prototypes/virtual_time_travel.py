"""Virtual Time Travel — MIDI knob selects a historical era.

MIDI contract: ``MidiInput.get(control, default=0.0)`` takes an integer CC
number and returns a normalised 0..1 value. Era selection scales that value
to the era list here (the old stub call passed ``val_min``/``val_max`` and
raised TypeError against the real input layer).

Image contract: ``dalle3.generate()`` returns ``(png_path, metadata)``, so the
path is decoded with the shared ``load_generated_image`` helper before it
reaches the renderer (which needs pixels, not a filename).
"""

import time

from src.lunar_tools_art import Manager
from src.lunar_tools_art.tools.images import load_generated_image

# Akai LPD8 knob default CC numbers (70-77 on the knob bank), 0..127 on the
# wire, normalised to 0..1 by MidiInput.get(). Only the CCs used here: CC70
# selects the era.
MIDI_CC = {"era": 70}


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

        if midi_device_name is not None:
            # MidiInput has no device selection: it binds the first available
            # input port. Assigning `device_name` on it was silently ignored.
            self.logger.info(
                "MIDI device selection is not configurable; MidiInput binds the "
                f"first available input port (requested {midi_device_name!r})."
            )
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

    def _era_index_from_cc(self):
        """Map the era CC (0..1) onto an index into `historical_eras`."""
        value = self.midi_input.get(MIDI_CC["era"], default=0.0)
        last = len(self.historical_eras) - 1
        return max(0, min(last, int(round(value * last))))

    def generate_historical_visual(self, era):
        prompt = f"A detailed, historically accurate visual representation of the {era} era. Focus on architecture, clothing, and atmosphere."
        try:
            path, _metadata = self.lunar_tools_art_manager.dalle3.generate(prompt)
            return load_generated_image(path)
        except Exception as e:
            self.logger.error(
                f"Error generating visual for era {era}: {e}", exc_info=True
            )
            return None  # Return a placeholder image on error

    def _step(self):
        """One full iteration: read the era CC and switch era when it changes.

        Returns True when the era changed (and an image was rendered).
        """
        new_era_index = self._era_index_from_cc()
        if new_era_index == self.current_era_index:
            return False

        self.current_era_index = new_era_index
        era = self.historical_eras[self.current_era_index]
        narration = f"Welcome to the {era} era."
        self.logger.info(narration)
        if self.text2speech is not None:
            try:
                self.text2speech.generate(narration)
            except Exception as e:
                self.logger.error(f"Error narrating era {era}: {e}", exc_info=True)

        image = self.generate_historical_visual(era)
        if image is not None:
            self.renderer.render(image)
        return True

    def run(self):
        self.logger.info("Virtual Time Travel: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Virtual Time Travel.")
                break

            self._step()

            time.sleep(self.loop_delay)  # Small delay to prevent busy-waiting


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    experience = TimeTravelExperience(lunar_tools_art_manager)
    experience.run()
