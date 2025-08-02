"""Example prototype demonstrating the use of PrototypeBase.

This example shows how to properly inherit from the base classes and implement
the required methods for a simple interactive art installation.
"""

import random
import time

import numpy as np
from PIL import Image, ImageDraw

from src.lunar_tools_art.prototype_base import InteractivePrototype


class ExampleBaseUsage(InteractivePrototype):
    """Example art installation showing base class usage.

    This prototype creates:
    - Animated particles that respond to user speech
    - Color changes based on audio input
    - Graceful shutdown handling
    - Proper resource management
    """

    def setup(self) -> None:
        """Initialize the art installation."""
        # Validate required configuration
        self.validate_config(["renderer.width", "renderer.height"])

        # Initialize art-specific parameters
        self.particles: list[tuple[float, float, float, float]] = []  # x, y, vx, vy
        self.background_color = (20, 20, 40)
        self.particle_color = (100, 150, 255)

        # Configuration with defaults
        self.max_particles = self.get_config("max_particles", 50)
        self.particle_speed = self.get_config("particle_speed", 2.0)
        self.speech_sensitivity = self.get_config("speech_sensitivity", 5.0)

        # Create initial particles
        self._create_initial_particles()

        self.logger.info(f"Art installation ready with {len(self.particles)} particles")

    def update(self) -> None:
        """Update the art installation state."""
        start_time = time.time()

        # Try to capture user speech (non-blocking)
        user_speech = self.get_user_speech(timeout=0.1)
        if user_speech:
            self._respond_to_speech(user_speech)

        # Update particle physics
        self._update_particles()

        # Render current state
        self._render_scene()

        # Log performance
        duration = time.time() - start_time
        self.log_performance("update_cycle", duration)

    def cleanup(self) -> None:
        """Clean up resources."""
        self.particles.clear()
        self.logger.info("Particles cleared, resources cleaned up")

    def _create_initial_particles(self) -> None:
        """Create initial set of particles."""
        width = self.get_config("renderer.width", 800)
        height = self.get_config("renderer.height", 600)

        for _ in range(self.max_particles):
            x = random.uniform(0, width)
            y = random.uniform(0, height)
            vx = random.uniform(-self.particle_speed, self.particle_speed)
            vy = random.uniform(-self.particle_speed, self.particle_speed)
            self.particles.append((x, y, vx, vy))

    def _update_particles(self) -> None:
        """Update particle positions with boundary wrapping."""
        width = self.get_config("renderer.width", 800)
        height = self.get_config("renderer.height", 600)

        updated_particles = []
        for x, y, vx, vy in self.particles:
            # Update position
            x += vx
            y += vy

            # Wrap around boundaries
            x = x % width
            y = y % height

            updated_particles.append((x, y, vx, vy))

        self.particles = updated_particles

    def _respond_to_speech(self, speech_text: str) -> None:
        """Respond to user speech by modifying the art."""
        self.logger.info(f"Responding to speech: '{speech_text}'")

        # Change colors based on speech content
        if "red" in speech_text.lower():
            self.particle_color = (255, 100, 100)
        elif "blue" in speech_text.lower():
            self.particle_color = (100, 100, 255)
        elif "green" in speech_text.lower():
            self.particle_color = (100, 255, 100)
        elif "yellow" in speech_text.lower():
            self.particle_color = (255, 255, 100)
        else:
            # Random color for other speech
            self.particle_color = (
                random.randint(100, 255),
                random.randint(100, 255),
                random.randint(100, 255),
            )

        # Add energy to particles based on speech length
        energy_boost = len(speech_text) * 0.1
        boosted_particles = []
        for x, y, vx, vy in self.particles:
            vx += random.uniform(-energy_boost, energy_boost)
            vy += random.uniform(-energy_boost, energy_boost)
            boosted_particles.append((x, y, vx, vy))

        self.particles = boosted_particles

    def _render_scene(self) -> None:
        """Render the current scene."""
        width = self.get_config("renderer.width", 800)
        height = self.get_config("renderer.height", 600)

        # Create canvas
        canvas = Image.new("RGB", (width, height), self.background_color)
        draw = ImageDraw.Draw(canvas)

        # Draw particles
        for x, y, _, _ in self.particles:
            particle_size = 3
            draw.ellipse(
                [
                    x - particle_size,
                    y - particle_size,
                    x + particle_size,
                    y + particle_size,
                ],
                fill=self.particle_color,
            )

        # Convert to numpy array and render
        canvas_array = np.array(canvas)
        self.renderer.render(canvas_array)


if __name__ == "__main__":
    from src.lunar_tools_art.manager import Manager

    # Create manager and run prototype
    manager = Manager()

    # Example configuration
    config = {"max_particles": 75, "particle_speed": 1.5, "speech_sensitivity": 3.0}

    prototype = ExampleBaseUsage(manager, **config)
    prototype.run()
