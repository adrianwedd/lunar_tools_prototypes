import time

import numpy as np
from PIL import Image, ImageDraw

from src.lunar_tools_art import Manager


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

        if midi_device_name == "akai_lpd8":
            self.logger.warning(
                "Using default MIDI device 'akai_lpd8'. Consider configuring a specific device name."
            )
        self.midi_input.device_name = midi_device_name  # Configure device name
        self.control_names = (
            control_names
            if control_names is not None
            else {"brightness": "A0", "contrast": "B0", "hue": "C0"}
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

    def run(self):
        self.logger.info("Dynamic Visuals: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Dynamic Visuals.")
                break

            brightness = self.midi_input.get(
                self.control_names["brightness"], val_min=0.5, val_max=1.5
            )
            contrast = self.midi_input.get(
                self.control_names["contrast"], val_min=0.5, val_max=1.5
            )
            hue = self.midi_input.get(self.control_names["hue"], val_min=0, val_max=1)

            # Generate visual based on MIDI input
            image = self.create_visual(brightness, contrast, hue)
            self.renderer.render(image)

            time.sleep(self.update_interval)  # Update visuals every 100ms


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    visualizer = DynamicVisualizer(lunar_tools_art_manager)
    visualizer.run()
