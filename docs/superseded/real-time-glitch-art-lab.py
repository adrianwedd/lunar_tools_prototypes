import json  # Import json here for local testing if needed
import random
import time

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from src.lunar_tools_art import Manager


class RealTimeGlitchArtLab:
    def __init__(self, lunar_tools_art_manager: Manager, loop_delay=0.066):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.webcam = self.lunar_tools_art_manager.webcam
        self.renderer = self.lunar_tools_art_manager.renderer
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.glitch_types = [
            "pixel_sort",
            "color_channel_shift",
            "scanline_interruption",
            "data_moshing_simulated",
        ]
        self.last_glitch_suggestion_time = 0
        self.glitch_suggestion_interval = 10  # Seconds between AI glitch suggestions
        self.loop_delay = loop_delay

    def _apply_glitch_transform(self, image, glitch_type, intensity):
        img_pil = Image.fromarray(image)
        width, height = img_pil.size

        if glitch_type == "pixel_sort":
            # Simple pixel sort: sort rows of pixels
            for y in range(height):
                row = [img_pil.getpixel((x, y)) for x in range(width)]
                row.sort(
                    key=lambda p: p[0] * intensity
                )  # Sort by red channel with intensity
                for x, pixel in enumerate(row):
                    img_pil.putpixel((x, y), pixel)
        elif glitch_type == "color_channel_shift":
            # Shift color channels
            r, g, b = img_pil.split()
            shift_amount = int(intensity * 20)
            r = ImageOps.roll(r, shift=shift_amount)
            g = ImageOps.roll(g, shift=-shift_amount)
            img_pil = Image.merge("RGB", (r, g, b))
        elif glitch_type == "scanline_interruption":
            # Introduce random horizontal lines of noise
            draw = ImageDraw.Draw(img_pil)
            for _ in range(int(intensity * 10)):
                y = random.randint(0, height - 1)
                x1 = random.randint(0, width // 2)
                x2 = random.randint(width // 2, width - 1)
                color = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                )
                draw.line([(x1, y), (x2, y)], fill=color, width=random.randint(1, 3))
        elif glitch_type == "data_moshing_simulated":
            # Simulate data moshing by block-swapping
            block_size = int(intensity * 50) + 10
            if block_size > min(width, height) // 2:
                block_size = min(width, height) // 2

            for _ in range(int(intensity * 5)):
                x1, y1 = random.randint(0, width - block_size), random.randint(
                    0, height - block_size
                )
                x2, y2 = random.randint(0, width - block_size), random.randint(
                    0, height - block_size
                )

                region1 = img_pil.crop((x1, y1, x1 + block_size, y1 + block_size))
                region2 = img_pil.crop((x2, y2, x2 + block_size, y2 + block_size))

                img_pil.paste(region2, (x1, y1, x1 + block_size, y1 + block_size))
                img_pil.paste(region1, (x2, y2, x2 + block_size, y2 + block_size))

        return np.array(img_pil)

    def _get_glitch_suggestion_from_gpt4(self):
        prompt = 'Suggest a glitch type and intensity for real-time video processing. Choose from: pixel_sort, color_channel_shift, scanline_interruption, data_moshing_simulated. Provide a float intensity between 0.1 and 1.0. Respond in JSON format: {"glitch_type": "pixel_sort", "intensity": 0.7}.'
        self.logger.info("Requesting glitch suggestion from GPT-4...")
        try:
            response = self.gpt4.generate(prompt)
            suggestion = json.loads(response)
            return suggestion
        except json.JSONDecodeError as e:
            self.logger.error(
                f"Error decoding JSON from GPT-4 response: {e}", exc_info=True
            )
            self.logger.error(f"GPT-4 response: {response}")
            return None
        except Exception as e:
            self.logger.error(
                f"Error getting glitch suggestion from GPT-4: {e}", exc_info=True
            )
            return None

    def run(self):
        self.logger.info("Real-Time Glitch Art Lab: Press 'q' to quit.")
        current_glitch_type = random.choice(self.glitch_types)
        current_intensity = random.uniform(0.1, 1.0)

        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Real-Time Glitch Art Lab.")
                break

            current_time = time.time()
            if (
                current_time - self.last_glitch_suggestion_time
                > self.glitch_suggestion_interval
            ):
                suggestion = self._get_glitch_suggestion_from_gpt4()
                if suggestion and suggestion["glitch_type"] in self.glitch_types:
                    current_glitch_type = suggestion["glitch_type"]
                    current_intensity = suggestion["intensity"]
                    self.logger.info(
                        f"AI suggested glitch: {current_glitch_type} with intensity {current_intensity:.2f}"
                    )
                self.last_glitch_suggestion_time = current_time

            try:
                frame = self.webcam.get_img()
                if frame is not None:
                    glitched_frame = self._apply_glitch_transform(
                        frame, current_glitch_type, current_intensity
                    )
                    self.renderer.render(glitched_frame)
                else:
                    self.logger.warning("No frame captured from webcam.")
            except Exception as e:
                self.logger.error(
                    f"Error processing/rendering frame: {e}", exc_info=True
                )

            time.sleep(self.loop_delay)  # Aim for ~15 FPS (1/15 = 0.066)


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    lab = RealTimeGlitchArtLab(lunar_tools_art_manager)
    lab.run()
