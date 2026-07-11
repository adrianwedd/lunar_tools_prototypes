# Voice-Activated Cosmic Soundscape Prototype
"""Voice-Activated Cosmic Soundscape.

Listens for a spoken phrase, maps its words to a cosmic palette and celestial
motifs, and renders a generated visual of the resulting soundscape. Louder,
longer phrases pull the imagery toward energetic nebulae; quiet, short ones
toward still deep-space fields.
"""

import time

from src.lunar_tools_art.prototype_base import InteractivePrototype

PALETTES = {
    "calm": "deep indigo and silver starlight",
    "warm": "amber nebula glow with golden dust",
    "cold": "glacial blue ion trails and pale cyan auroras",
    "storm": "violent magenta plasma storms and dark voids",
}

MOTIF_KEYWORDS = {
    "star": "a dense field of newborn stars",
    "moon": "a cratered moon rising over a gas giant",
    "sun": "a flaring binary sun",
    "dark": "a lightless void bending distant galaxies",
    "dream": "drifting luminescent stardust rivers",
    "storm": "a churning plasma storm",
    "ocean": "waves of interstellar gas like a cosmic sea",
    "fire": "a supernova blooming in slow motion",
    "ice": "frozen comet shards catching starlight",
    "love": "two spiral galaxies slowly merging",
}


class CosmicSoundscape(InteractivePrototype):
    """Turns spoken phrases into cosmic visuals."""

    def setup(self) -> None:
        self.image_gen = getattr(self.manager, "image_gen", None)
        self.listen_timeout = self.get_config("listen_timeout", 4.0)
        self.idle_delay = self.get_config("idle_delay", 1.0)
        self.last_phrase = None
        self.logger.info("Cosmic Soundscape ready - speak a phrase to shape the cosmos")

    def update(self) -> None:
        start_time = time.time()

        phrase = self._listen()
        if not phrase:
            time.sleep(self.idle_delay)
            return

        self.last_phrase = phrase
        prompt = self._build_prompt(phrase)
        self.logger.info(f"Cosmic prompt: {prompt}")

        image = self._generate_visual(prompt)
        if image is not None:
            self.renderer.render(image)

        self.log_performance("soundscape_cycle", time.time() - start_time)

    def cleanup(self) -> None:
        self.logger.info("Cosmic Soundscape drifting back into silence")

    def _listen(self) -> str | None:
        try:
            phrase = self.speech2text.transcribe(duration=self.listen_timeout)
        except Exception as e:
            self.logger.error(f"Speech capture failed: {e}")
            return None
        if phrase:
            self.logger.info(f"Heard: '{phrase}'")
            return str(phrase)
        return None

    def _build_prompt(self, phrase: str) -> str:
        words = phrase.lower().split()

        motifs = [
            motif
            for keyword, motif in MOTIF_KEYWORDS.items()
            if any(keyword in word for word in words)
        ]
        if not motifs:
            motifs = ["an uncharted nebula echoing the speaker's words"]

        palette = self._pick_palette(phrase, words)
        energy = "high-energy, swirling" if len(words) > 6 else "serene, drifting"

        return (
            f"A cosmic soundscape visualization: {', '.join(motifs)}, "
            f"rendered in {palette}, {energy} composition, inspired by the "
            f'spoken phrase "{phrase}", cinematic deep space art'
        )

    def _pick_palette(self, phrase: str, words: list[str]) -> str:
        lowered = phrase.lower()
        if any(w in lowered for w in ("storm", "rage", "loud", "fire")):
            return PALETTES["storm"]
        if any(w in lowered for w in ("warm", "sun", "gold", "love")):
            return PALETTES["warm"]
        if any(w in lowered for w in ("ice", "cold", "winter", "frost")):
            return PALETTES["cold"]
        return PALETTES["calm"]

    def _generate_visual(self, prompt: str):
        if self.image_gen is None:
            self.logger.warning("No image generator available; skipping render")
            return None
        try:
            result = self.image_gen.generate(prompt)
        except Exception as e:
            self.logger.error(f"Image generation failed: {e}")
            return None
        if isinstance(result, tuple):
            return result[0]
        return result


if __name__ == "__main__":
    from src.lunar_tools_art import Manager

    CosmicSoundscape(Manager()).run()
