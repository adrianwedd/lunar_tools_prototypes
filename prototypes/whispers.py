import random
import time
from collections import deque

import numpy as np
from PIL import Image, ImageDraw


class Particle:
    def __init__(self, x, y, vx, vy, color, size, trail_length):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.size = size
        self.trail = deque(maxlen=trail_length)

    def update(self):
        self.trail.append((self.x, self.y))
        self.x += self.vx
        self.y += self.vy
        # Simulate Brownian motion (random small changes to velocity)
        self.vx += random.uniform(-0.1, 0.1)
        self.vy += random.uniform(-0.1, 0.1)
        # Dampen velocity to prevent particles from flying off too fast
        self.vx *= 0.98
        self.vy *= 0.98

    def draw(self, draw):
        # Draw particle
        draw.ellipse(
            [
                self.x - self.size,
                self.y - self.size,
                self.x + self.size,
                self.y + self.size,
            ],
            fill=self.color,
        )
        # Draw trail
        for i, (tx, ty) in enumerate(self.trail):
            alpha = int(255 * (i / self.trail.maxlen))
            trail_color = self.color[:3] + (alpha,)
            draw.ellipse(
                [
                    tx - self.size / 2,
                    ty - self.size / 2,
                    tx + self.size / 2,
                    ty + self.size / 2,
                ],
                fill=trail_color,
            )


class Whispers:
    def __init__(self, lunar_tools_art_manager):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.renderer = self.lunar_tools_art_manager.renderer
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.logger = self.lunar_tools_art_manager.logger
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input

        self.webcam = self.lunar_tools_art_manager.webcam
        self.previous_frame = None

        self.particles = []
        self.zones = [
            {
                "x": 100,
                "y": 100,
                "width": 200,
                "height": 200,
                "movement_detected": False,
            },
            {
                "x": 500,
                "y": 100,
                "width": 200,
                "height": 200,
                "movement_detected": False,
            },
            {
                "x": 300,
                "y": 300,
                "width": 200,
                "height": 200,
                "movement_detected": False,
            },
        ]

    def _detect_movement(self, zone_index):
        current_frame = self.webcam.get_img()
        if current_frame is None:
            self.logger.warning("No frame captured from webcam for movement detection.")
            return False

        # Convert to grayscale for simpler comparison
        current_gray = np.mean(current_frame, axis=2).astype(np.float32)

        if self.previous_frame is None:
            self.previous_frame = current_gray
            return False

        # Calculate absolute difference between current and previous frame
        frame_diff = np.abs(current_gray - self.previous_frame)

        # Define the zone coordinates
        zone = self.zones[zone_index]
        x1, y1 = zone["x"], zone["y"]
        x2, y2 = zone["x"] + zone["width"], zone["y"] + zone["height"]

        # Extract the zone from the difference image
        zone_diff = frame_diff[y1:y2, x1:x2]

        # Calculate the mean difference within the zone
        mean_diff = np.mean(zone_diff)

        # Update previous frame for next iteration
        self.previous_frame = current_gray

        # Define a threshold for movement detection
        movement_threshold = 10.0  # This value might need tuning

        if mean_diff > movement_threshold:
            return True
        else:
            return False

    def _generate_sound(self):
        freq = np.random.uniform(200, 2000)
        duration = np.random.uniform(0.1, 0.5)

        # Generate a short, abstract sound description
        sound_description = random.choice(
            [
                "a soft, ethereal hum",
                "a gentle, shimmering chime",
                "a low, resonant thrum",
                "a high-pitched, delicate whisper",
            ]
        )
        self.logger.info(f"Generating sound: {sound_description}")

        try:
            # Generate speech from the description
            filename = f".output/whisper_sound_{int(time.time())}.mp3"
            self.lunar_tools_art_manager.text2speech.generate(
                sound_description, filename=filename
            )
            self.lunar_tools_art_manager.sound_player.play_sound(filename)
        except Exception as e:
            self.logger.error(f"Error generating or playing sound: {e}", exc_info=True)

    def _create_burst_of_particles(self, center_x, center_y, count):
        for _ in range(count):
            x = center_x + random.uniform(-20, 20)
            y = center_y + random.uniform(-20, 20)
            vx = random.uniform(-5, 5)
            vy = random.uniform(-5, 5)
            color = (
                random.randint(150, 255),
                random.randint(150, 255),
                random.randint(150, 255),
                255,
            )
            size = random.randint(3, 8)
            trail_length = random.randint(10, 30)
            self.particles.append(Particle(x, y, vx, vy, color, size, trail_length))

    def run(self):
        self.logger.info("Whispers: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Whispers.")
                break

            # Update particle positions
            for particle in list(
                self.particles
            ):  # Iterate over a copy to allow removal
                particle.update()
                # Remove particles that go off-screen
                if not (
                    0 < particle.x < self.renderer.width
                    and 0 < particle.y < self.renderer.height
                ):
                    self.particles.remove(particle)

            # Check for movement in zones and react
            for i, zone in enumerate(self.zones):
                if self._detect_movement(i):
                    self.logger.info(f"Movement detected in zone {i+1}")
                    self._generate_sound()
                    self._create_burst_of_particles(
                        zone["x"] + zone["width"] // 2,
                        zone["y"] + zone["height"] // 2,
                        50,
                    )

            # Draw everything
            canvas_image = Image.new(
                "RGB", (self.renderer.width, self.renderer.height), color=(0, 0, 0)
            )  # Black background
            draw = ImageDraw.Draw(canvas_image, "RGBA")

            for particle in self.particles:
                particle.draw(draw)

            # Draw zones (for debugging/visualization)
            for zone in self.zones:
                draw.rectangle(
                    [
                        zone["x"],
                        zone["y"],
                        zone["x"] + zone["width"],
                        zone["y"] + zone["height"],
                    ],
                    outline=(255, 0, 0, 100),
                    width=2,
                )

            self.renderer.render(np.array(canvas_image))

            time.sleep(0.05)  # Small delay for animation


if __name__ == "__main__":
    from src.lunar_tools_art.manager import Manager

    lunar_tools_art_manager = Manager()
    whispers_app = Whispers(lunar_tools_art_manager)
    whispers_app.run()
