"""Lunar Tools Art - Interactive audiovisual art installations.

This package provides tools and base classes for creating AI-driven art installations
that combine speech-to-text, text generation, image synthesis, and real-time rendering.
"""

from .manager import Manager
from .prototype_base import AIPrototype, InteractivePrototype, PrototypeBase

__all__ = ["Manager", "PrototypeBase", "InteractivePrototype", "AIPrototype"]
__version__ = "0.1.0"
