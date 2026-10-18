"""MIDI-controlled generative visuals.

MIDI contract: ``MidiInput.get(control, default=0.0)`` takes an integer CC
number and returns a normalised 0..1 value (the old stub signature accepted
control names and ``val_min``/``val_max``; that call raised TypeError on the
real input layer). All range mapping now happens here.
"""

import time

import numpy as np
from PIL import Image, ImageDraw

from src.lunar_tools_art import Manager

# Akai LPD8 knob default CC numbers (70-77 on the knob bank), 0..127 on the
# wire, normalised to 0..1 by MidiInput.get(). Only the CCs used here.
MIDI_CC = {"brightness": 70, "contrast": 71, "hue": 72}

# Neutral knob position: brightness/contrast are scaled to 0.5..1.5 so a
# centred knob leaves the image untouched (multiplier 1.0), and a device-free
# MidiInput (which returns the default) still renders something visible.
NEUTRAL = 0.5


class DynamicVisualizer:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        midi_device_name="akai_lpd8",
        control_names=None,
        update_interval=0.1,
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.midi_input = self.lunar_tools_art_manager.midi_input
        self.renderer = self.lunar_tools_art_manager.renderer
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.update_interval = update_interval

        if midi_device_name is not None:
            # MidiInput has no device selection: it binds the first available
            # input port. Assigning `device_name` on it was silently ignored.
            self.logger.info(
                "MIDI device selection is not configurable; MidiInput binds the "
                f"first available input port (requested {midi_device_name!r})."
            )
        # control name -> integer CC number (defaults to MIDI_CC).
        self.control_names = (
            control_names if control_names is not None else dict(MIDI_CC)
        )

    def create_visual(self, brightness, contrast, hue):
        # Create a base image (e.g., a gradient or a simple shape)
        width, height = self.renderer.width, self.renderer.height
        image = Image.new("RGB", (width, height), color=(0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Example: Draw a colored circle whose properties change with MIDI inputs
        radius = int(min(width, height) / 4 * brightness)  # Brightness affects size
        center_x, center_y = width // 2, height // 2

        # Hue affects color
        # Convert HUE (0-1) to RGB
        # This is a simplified conversion, a full HSL/HSV to RGB conversion would be more complex
        r, g, b = 0, 0, 0
        if 0 <= hue < 1 / 6:
            r, g, b = 255, int(hue * 6 * 255), 0
        elif 1 / 6 <= hue < 2 / 6:
            r, g, b = int((2 / 6 - hue) * 6 * 255), 255, 0
        elif 2 / 6 <= hue < 3 / 6:
            r, g, b = 0, 255, int((hue - 2 / 6) * 6 * 255)
        elif 3 / 6 <= hue < 4 / 6:
            r, g, b = 0, int((4 / 6 - hue) * 6 * 255), 255
        elif 4 / 6 <= hue < 5 / 6:
            r, g, b = int((hue - 4 / 6) * 6 * 255), 0, 255
        else:
            r, g, b = 255, 0, int((1 - hue) * 6 * 255)

        fill_color = (r, g, b)

        draw.ellipse(
            [
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
            ],
            fill=fill_color,
        )

        # Apply contrast (simplified: adjust pixel values directly)
        # This is a very basic way to apply contrast and might not be visually accurate
        image_array = np.array(image).astype(np.float32)
        image_array = image_array * contrast
        image_array = np.clip(image_array, 0, 255).astype(np.uint8)

        return Image.fromarray(image_array)

    def _read_controls(self):
        """Read the three CCs and map 0..1 to the visual's parameter ranges."""
        brightness_cc = self.control_names["brightness"]
        contrast_cc = self.control_names["contrast"]
        hue_cc = self.control_names["hue"]
        # 0..1 -> 0.5..1.5 (1.0 at the neutral/centre knob position).
        brightness = NEUTRAL + self.midi_input.get(brightness_cc, default=NEUTRAL)
        contrast = NEUTRAL + self.midi_input.get(contrast_cc, default=NEUTRAL)
        # 0..1 straight through.
        hue = self.midi_input.get(hue_cc, default=0.0)
        return brightness, contrast, hue

    def _step(self):
        """One full frame: read MIDI, draw, render. Returns the rendered image."""
        brightness, contrast, hue = self._read_controls()
        image = self.create_visual(brightness, contrast, hue)
        self.renderer.render(image)
        return image

    def run(self):
        self.logger.info("Dynamic Visuals: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Dynamic Visuals.")
                break

            self._step()

            time.sleep(self.update_interval)  # Update visuals every 100ms


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    visualizer = DynamicVisualizer(lunar_tools_art_manager)
    visualizer.run()
