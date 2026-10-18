"""Evolving Cosmic Mural — AI-generated cosmic scene that blends on a timer.

MIDI contract: ``MidiInput.get(control, default=0.0)`` takes an integer CC
number and returns a normalised 0..1 value. The eight knobs are read as
integer CCs and thresholded here (the old stub call passed ``val_min``/
``val_max`` and strings like "A0", which raised TypeError against the real
input layer).

Image contract: ``sdxl_lcm.generate()`` returns ``(png_path, metadata)``, so
every result is decoded with the shared ``load_generated_image`` helper before
being blended or rendered — ``Image.blend`` needs pixels, not a filename.
"""

import time

import numpy as np
from PIL import Image

from src.lunar_tools_art import Manager
from src.lunar_tools_art.tools.images import load_generated_image

# Akai LPD8 knob default CC numbers: CC70-77 for the eight knobs, 0..127 on
# the wire, normalised to 0..1 by MidiInput.get(). Knob i owns phrase i.
MIDI_CC_FADERS = tuple(range(70, 78))

# A knob crossing above this value latches its modifier phrase once.
SLIDER_THRESHOLD = 0.5

# One phrase per knob, appended when that knob is pushed up.
MODIFIER_PHRASES = (
    "with a supernova explosion",
    "featuring a black hole",
    "with swirling cosmic dust",
    "showing a planetary alignment",
    "with a comet streaking across",
    "featuring an alien space station",
    "with aurora-like phenomenon",
    "showing the birth of a new star",
)


class EvolvingCosmicMural:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        midi_device_name="akai_lpd8",
        blend_speed=0.1,
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.sdxl_lcm = self.lunar_tools_art_manager.sdxl_lcm
        self.renderer = self.lunar_tools_art_manager.renderer
        self.midi_input = self.lunar_tools_art_manager.midi_input
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.blend_speed = blend_speed

        if midi_device_name is not None:
            # MidiInput has no device selection: it binds the first available
            # input port. Assigning `device_name` on it was silently ignored.
            self.logger.info(
                "MIDI device selection is not configurable; MidiInput binds the "
                f"first available input port (requested {midi_device_name!r})."
            )
        self.base_prompt = "A vast cosmic scene with galaxies, nebulae, and stars"
        self.current_image = None
        self.modifiers = []
        self.last_generation_time = 0
        self.generation_interval = 10  # Generate a new image every 10 seconds
        self.midi_slider_states = [
            False
        ] * 8  # To track if a slider has crossed the threshold
        # Sleep seam so tests can run a full iteration (including the 30-frame
        # cross-fade) without real delays; run() keeps using time.sleep.
        self._pause = time.sleep

    def generate_cosmic_scene(self):
        prompt = self.base_prompt + ", " + ", ".join(self.modifiers)
        try:
            path, _metadata = self.sdxl_lcm.generate(prompt)
            return load_generated_image(path)
        except Exception as e:
            self.logger.error(f"Error generating image: {e}", exc_info=True)
            return None

    def blend_images(self, img1, img2, alpha):
        return Image.blend(img1, img2, alpha)

    def _read_modifiers(self):
        """Latch a modifier phrase for each knob pushed above the threshold."""
        for i, cc in enumerate(MIDI_CC_FADERS):
            slider_value = self.midi_input.get(cc, default=0.0)
            if slider_value > SLIDER_THRESHOLD and not self.midi_slider_states[i]:
                self.modifiers.append(MODIFIER_PHRASES[i])
                self.midi_slider_states[i] = True
            elif slider_value <= SLIDER_THRESHOLD and self.midi_slider_states[i]:
                self.midi_slider_states[i] = False

    def _step(self, pause=True):
        """One full iteration: poll knobs, maybe regenerate + cross-fade, render.

        ``pause=False`` skips the per-blend-frame sleep so a whole iteration can
        be exercised deterministically in tests.
        """
        self._read_modifiers()

        current_time = time.time()
        if current_time - self.last_generation_time > self.generation_interval:
            new_image = self.generate_cosmic_scene()
            self.last_generation_time = current_time
            self.modifiers = []  # Reset modifiers after generating new image

            if new_image is not None:
                if self.current_image is not None:
                    # Blend the new image with the current image
                    for alpha in np.linspace(
                        0, 1, 30
                    ):  # 30 frames for smooth transition
                        blended_image = self.blend_images(
                            self.current_image, new_image, alpha
                        )
                        try:
                            self.renderer.render(np.array(blended_image))
                        except Exception as e:
                            self.logger.error(
                                f"Error rendering blended image: {e}", exc_info=True
                            )
                        if pause:
                            self._pause(
                                self.blend_speed
                            )  # Adjust for desired transition speed
                self.current_image = new_image
            else:
                self.logger.info("Skipping image blending due to generation error.")

        # Render the current image
        if self.current_image is not None:
            try:
                self.renderer.render(np.array(self.current_image))
            except Exception as e:
                self.logger.error(
                    f"Error rendering current image: {e}", exc_info=True
                )

    def run(self):
        self.logger.info("Evolving Cosmic Mural: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Evolving Cosmic Mural.")
                break

            self._step()

            time.sleep(0.1)  # Small delay to prevent excessive CPU usage


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    mural = EvolvingCosmicMural(lunar_tools_art_manager)
    mural.run()
