import time

import librosa
import numpy as np
from PIL import Image

from src.lunar_tools_art import Manager
from utils import run_until_quit


class AudioReactiveFractalForest:
    def __init__(self, lunar_tools_art_manager: Manager, loop_delay=0.1):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.audio_recorder = self.lunar_tools_art_manager.audio_recorder
        self.renderer = self.lunar_tools_art_manager.renderer
        self.gpt4 = self.lunar_tools_art_manager.gpt4  # For color mapping requests
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.loop_delay = loop_delay

        self.fractal_params = {
            "zoom": 1.0,
            "iteration_depth": 50,
            "color_palette": [(0, 0, 0), (255, 255, 255)],  # Default black and white
        }

    def _process_audio_frame(self, audio_data_path):
        try:
            y, sr = librosa.load(audio_data_path)

            # Compute STFT
            stft = np.abs(librosa.stft(y))

            # Extract dominant frequency bands (simplified: mean of magnitude in bands)
            # Define frequency bands (e.g., low, mid, high)
            freqs = librosa.fft_frequencies(sr=sr)
            low_freq_band = stft[(freqs >= 0) & (freqs < 500)].mean()
            mid_freq_band = stft[(freqs >= 500) & (freqs < 2000)].mean()
            high_freq_band = stft[(freqs >= 2000)].mean()

            # Map frequency metrics to fractal parameters
            # Normalize values to a reasonable range for fractal parameters
            self.fractal_params["zoom"] = (
                1.0 + (high_freq_band - low_freq_band) * 0.001
            )  # Example mapping
            self.fractal_params["iteration_depth"] = int(
                50 + mid_freq_band * 0.1
            )  # Example mapping

            # Prompt GPT-4 for color mapping based on frequency metrics
            prompt = f"Given audio frequency metrics: Low={low_freq_band:.2f}, Mid={mid_freq_band:.2f}, High={high_freq_band:.2f}. Suggest a color palette (e.g., 'cool blues, warm oranges', 'fiery reds, golden yellows')."
            color_suggestion = self.gpt4.generate(prompt)
            self.logger.info(f"GPT-4 color suggestion: {color_suggestion}")

            # Convert GPT-4 response to a color palette (simplified parsing)
            if "cool blues" in color_suggestion.lower():
                self.fractal_params["color_palette"] = [
                    (0, 0, 50),
                    (0, 0, 200),
                    (255, 100, 0),
                    (255, 200, 0),
                ]
            elif "vibrant greens" in color_suggestion.lower():
                self.fractal_params["color_palette"] = [
                    (0, 50, 0),
                    (0, 200, 0),
                    (100, 0, 100),
                    (200, 0, 200),
                ]
            elif "fiery reds" in color_suggestion.lower():
                self.fractal_params["color_palette"] = [
                    (50, 0, 0),
                    (200, 0, 0),
                    (255, 200, 0),
                    (255, 255, 0),
                ]
            else:  # Default or monochromatic
                self.fractal_params["color_palette"] = [
                    (50, 50, 50),
                    (150, 150, 150),
                    (0, 100, 100),
                    (0, 200, 200),
                ]

        except Exception as e:
            self.logger.error(f"Error processing audio frame: {e}", exc_info=True)

    def _render_fractal(self):
        width, height = self.renderer.width, self.renderer.height
        image_array = np.zeros((height, width, 3), dtype=np.uint8)

        # Mandelbrot set calculation
        for x in range(width):
            for y in range(height):
                # Map pixel to complex plane
                zx, zy = 0.0, 0.0
                c_real = (x - width / 2) * 4.0 / width / self.fractal_params["zoom"]
                c_imag = (y - height / 2) * 4.0 / width / self.fractal_params["zoom"]

                iteration = 0
                for i in range(int(self.fractal_params["iteration_depth"])):
                    zx2 = zx * zx
                    zy2 = zy * zy
                    if zx2 + zy2 > 4.0:
                        break
                    zy = 2.0 * zx * zy + c_imag
                    zx = zx2 - zy2 + c_real
                    iteration += 1

                # Map iteration count to color from the palette
                color_index = (
                    int(iteration % len(self.fractal_params["color_palette"]))
                    if iteration < self.fractal_params["iteration_depth"]
                    else 0
                )
                color = self.fractal_params["color_palette"][color_index]
                image_array[y, x] = color

        return Image.fromarray(image_array)

    def _loop_callback(self):
        # Capture live microphone input in short frames
        self.logger.info("Capturing audio frame...")
        audio_file_path = ".output/temp_audio_frame.wav"
        self.audio_recorder.start_recording(audio_file_path)
        time.sleep(0.1)  # Short frame
        self.audio_recorder.stop_recording()
        self._process_audio_frame(audio_file_path)

        # Render the fractal based on updated parameters
        fractal_image = self._render_fractal()
        self.renderer.render(fractal_image)

    def run(self):
        run_until_quit(
            self._loop_callback,
            self.lunar_tools_art_manager,
            fps=int(1.0 / self.loop_delay),
        )


if __name__ == "__main__":
    from PIL import Image  # Import here for local testing

    lunar_tools_art_manager = Manager()
    forest = AudioReactiveFractalForest(lunar_tools_art_manager)
    forest.run()
