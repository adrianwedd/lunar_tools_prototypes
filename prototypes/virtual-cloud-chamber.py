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


class VirtualCloudChamber:
    def __init__(self, lunar_tools_art_manager, loop_delay=0.05):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.text2speech = self.lunar_tools_art_manager.text2speech
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.renderer = self.lunar_tools_art_manager.renderer
        self.logger = self.lunar_tools_art_manager.logger
        self.particles = []
        self.last_narration_time = 0
        self.narration_interval = 30  # Narrate every 30 seconds
        self.background_image = self._generate_vapor_background()
        self.loop_delay = loop_delay

    def _generate_vapor_background(self):
        # Simple procedural vapor-like background
        img = Image.new(
            "RGBA", (self.renderer.width, self.renderer.height), color=(50, 50, 70, 255)
        )  # Ensure background is RGBA
        draw = ImageDraw.Draw(img)
        for _ in range(100):
            x = random.randint(0, self.renderer.width)
            y = random.randint(0, self.renderer.height)
            radius = random.randint(50, 200)
            color = (
                random.randint(80, 120),
                random.randint(80, 120),
                random.randint(100, 150),
                random.randint(20, 80),
            )  # Semi-transparent blueish
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)
        return img

    def _create_new_particle(self):
        x = random.randint(0, self.renderer.width)
        y = random.randint(0, self.renderer.height)
        vx = random.uniform(-5, 5)
        vy = random.uniform(-5, 5)
        color = (
            random.randint(150, 255),
            random.randint(150, 255),
            random.randint(150, 255),
            255,
        )  # Whiteish, opaque
        size = random.randint(3, 8)
        trail_length = random.randint(10, 30)
        self.particles.append(Particle(x, y, vx, vy, color, size, trail_length))

    def _narrate_particle_journeys(self):
        if not self.particles:
            return

        # Select a few interesting particles (e.g., longest trail, fastest, etc.)
        interesting_particles = random.sample(
            self.particles, min(len(self.particles), 3)
        )
        descriptions = []
        for p in interesting_particles:
            descriptions.append(
                f"A particle starting at ({int(p.trail[0][0])}, {int(p.trail[0][1])}) drifting towards ({int(p.x)}, {int(p.y)}) with a {len(p.trail)}-step trail."
            )

        prompt = (
            "Narrate the journeys of these particles in a poetic and scientific tone:\n\n"
            + "\n".join(descriptions)
        )
        self.logger.info("Requesting narration from GPT-4...")
        try:
            narration = self.gpt4.generate(prompt)
            self.logger.info(f"Narration: {narration}")
            self.text2speech.generate(
                narration, filename=".output/narration.mp3"
            )  # Generate speech to a file
            self.lunar_tools_art_manager.sound_player.play_sound(
                ".output/narration.mp3"
            )  # Play the generated speech
        except Exception as e:
            self.logger.error(
                f"Error generating or playing narration: {e}", exc_info=True
            )

    def run(self):
        self.logger.info(
            "Virtual Cloud Chamber: Press 'q' to quit. Speak or press any key to create particles."
        )

        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Virtual Cloud Chamber.")
                break

            # Trigger new particle creation on speech or keyboard input
            speech_detected = False
            try:
                speech_text = self.speech2text.transcribe(
                    duration=1
                )  # Short recording for quick detection
                if (
                    speech_text and len(speech_text.split()) > 1
                ):  # Basic check for meaningful speech
                    speech_detected = True
                    self.logger.info(f"Speech detected: {speech_text}")
            except Exception as e:
                self.logger.debug(f"Speech detection error: {e}")
                pass  # Ignore speech errors for continuous operation

            if speech_detected or self.keyboard_input.is_any_key_pressed():
                self._create_new_particle()

            # Update and draw particles
            current_canvas = self.background_image.copy()
            draw = ImageDraw.Draw(current_canvas, "RGBA")  # Enable alpha for trails
            for particle in list(
                self.particles
            ):  # Iterate over a copy to allow removal
                particle.update()
                particle.draw(draw)
                # Remove particles that go off-screen
                if not (
                    0 < particle.x < self.renderer.width
                    and 0 < particle.y < self.renderer.height
                ):
                    self.particles.remove(particle)

            self.renderer.render(np.array(current_canvas))

            # Periodically narrate particle journeys
            current_time = time.time()
            if current_time - self.last_narration_time > self.narration_interval:
                self._narrate_particle_journeys()
                self.last_narration_time = current_time

            time.sleep(self.loop_delay)  # Small delay for animation


if __name__ == "__main__":
    from src.lunar_tools_art.manager import Manager

    lunar_tools_art_manager = Manager()
    chamber = VirtualCloudChamber(lunar_tools_art_manager)
    chamber.run()
