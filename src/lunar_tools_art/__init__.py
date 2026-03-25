"""Lunar Tools Art - Interactive audiovisual art installations.

This package provides tools and base classes for creating AI-driven art installations
that combine speech-to-text, text generation, image synthesis, and real-time rendering.
"""

from .emotion import EmotionDetector, EmotionResult
from .llm_backends import LLMBackend, create_backend
from .manager import LunarToolsArtManager
from .prosody import ProsodyAnalyzer, ProsodyResult
from .prototype_base import AIPrototype, InteractivePrototype, PrototypeBase
from .voice_client import CloneResult, VoiceClient

# Backward compatibility alias
Manager = LunarToolsArtManager

__all__ = [
    "Manager",
    "LunarToolsArtManager",
    "PrototypeBase",
    "InteractivePrototype",
    "AIPrototype",
    "LLMBackend",
    "create_backend",
    "EmotionDetector",
    "EmotionResult",
    "ProsodyAnalyzer",
    "ProsodyResult",
    "VoiceClient",
    "CloneResult",
]
__version__ = "0.1.0"
