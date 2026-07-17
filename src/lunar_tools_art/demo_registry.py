"""Static registry of every public demo. THE source of truth for the CLI.

No prototype imports happen here — listing must be instant and side-effect
free. class_name is explicit because the filename→CamelCase convention is
false for 14 of 30 prototype files. Requirements were assigned by reading
each prototype's actual tool usage (speech2text/audio_recorder → mic,
sound_player → audio-out, webcam → camera, gpt4/llm_backend → llm,
dalle3/sdxl/flux/image_gen → image-gen, voice_client/text2speech →
afterwords, zmq → peer+network).
"""

from dataclasses import dataclass

CAPABILITIES = frozenset(
    {
        "mic",
        "audio-out",
        "camera",
        "renderer",
        "afterwords",
        "llm",
        "image-gen",
        "midi",
        "network",
        "peer",
        "assets",
    }
)

EXCLUDED_MODULES = {"__init__", "example_base_usage"}


@dataclass(frozen=True)
class Requirement:
    capability: str
    level: str = "required"  # or "optional"


@dataclass(frozen=True)
class ConfigKnob:
    key: str
    type: type
    default: object
    description: str


@dataclass(frozen=True)
class Demo:
    name: str
    module: str
    class_name: str
    description: str
    requirements: tuple = ()
    config_knobs: tuple = ()
    status: str = "works"  # headless-smoke status from PROTOTYPE_STATUS.md
    assets: tuple = ()  # files the demo expects to exist


def _req(*caps, optional=()):
    return tuple(
        Requirement(c, "optional" if c in optional else "required") for c in caps
    )


DEMOS = {
    d.name: d
    for d in [
        Demo(
            "acoustic-fingerprint-painter",
            "acoustic-fingerprint-painter",
            "AcousticFingerprintPainter",
            "Paints abstract brushstrokes driven by each visitor's voice fingerprint.",
            _req("mic", "renderer", optional=("llm",)),
        ),
        Demo(
            "ai-dream-interpreter-prototype",
            "ai-dream-interpreter-prototype",
            "AIDreamInterpreter",
            "Tell it a dream; it answers with an interpretation, imagery, and voice.",
            _req(
                "mic",
                "llm",
                "image-gen",
                "renderer",
                "audio-out",
                optional=("afterwords",),
            ),
        ),
        Demo(
            "ai-fashion-show-prototype",
            "ai-fashion-show-prototype",
            "AIFashionShow",
            "An endless AI runway: generated outfits parade across the screen.",
            _req("image-gen", "renderer"),
        ),
        Demo(
            "ai-mirror-of-truth",
            "ai-mirror-of-truth",
            "AiMirrorOfTruth",
            "Camera mirror with live emotion detection, prosody analysis, and a voice that answers what it sees.",
            _req(
                "camera",
                "mic",
                "llm",
                "renderer",
                "audio-out",
                optional=("afterwords",),
            ),
        ),
        Demo(
            "apocalypse-experience",
            "apocalypse_experience",
            "ApocalypseExperience",
            "Ambient end-times soundscape with AI-generated doom imagery.",
            _req("audio-out", "image-gen", "renderer", "assets"),
            assets=("apocalypse_ambient.mp3",),
        ),
        Demo(
            "audio-mirror",
            "audio_mirror",
            "AudioMirror",
            "Captures your voice, progressively clones it, and speaks personal insights back in your own voice.",
            _req("mic", "camera", "afterwords", "llm", "renderer"),
        ),
        Demo(
            "audio-reactive-fractal-forest",
            "audio-reactive-fractal-forest",
            "AudioReactiveFractalForest",
            "An evolving fractal forest whose shape and colors respond to ambient audio.",
            _req("mic", "renderer", optional=("llm",)),
        ),
        Demo(
            "augmented-audio-tours",
            "augmented_audio_tours",
            "AugmentedAudioTour",
            "Location-aware audio tour (vision-based positioning pending a vision LLM).",
            _req("camera", "audio-out", "assets", optional=("llm",)),
            status="degraded",
            assets=("section1_narration.mp3", "section2_music.mp3"),
        ),
        Demo(
            "chat-room-narrative-quilt",
            "chat-room-narrative-quilt",
            "ChatRoomNarrativeQuilt",
            "Weaves chat-room fragments into an AI-illustrated narrative quilt.",
            _req("llm", "image-gen", "renderer"),
        ),
        Demo(
            "collaborative-canvas",
            "collaborative-canvas",
            "CollaborativeCanvas",
            "Two-machine shared canvas over ZMQ.",
            _req("peer", "network", "renderer", optional=("llm",)),
        ),
        Demo(
            "collaborative-art",
            "collaborative_art",
            "CollaborativeArtServer",
            "ZMQ server half of the collaborative art pair.",
            _req("peer", "network", "renderer", optional=("image-gen",)),
        ),
        Demo(
            "cosmic-soundscape",
            "cosmic-soundscape",
            "CosmicSoundscape",
            "Maps a spoken phrase to celestial motifs and renders a cosmic visual.",
            _req("mic", "image-gen", "renderer"),
        ),
        Demo(
            "data-driven-cityscape",
            "data-driven-cityscape",
            "DataDrivenCityscape",
            "Generative skyline that morphs with live weather (synthetic data offline).",
            _req("renderer", optional=("network", "llm")),
        ),
        Demo(
            "dynamic-visuals",
            "dynamic_visuals",
            "DynamicVisualizer",
            "MIDI-controlled generative visuals.",
            _req("midi", "renderer"),
        ),
        Demo(
            "emotional-landscape-generator-prototype",
            "emotional-landscape-generator-prototype",
            "EmotionalLandscapeGenerator",
            "Reads the room's emotion and paints a landscape to match.",
            _req("camera", "mic", "llm", "image-gen", "renderer"),
        ),
        Demo(
            "escape-room",
            "escape_room",
            "EscapeRoomGame",
            "Voice-driven escape room with AI intent parsing and audio cues.",
            _req(
                "mic",
                "llm",
                "image-gen",
                "audio-out",
                "renderer",
                "assets",
            ),
            assets=("correct_answer.mp3", "hint.mp3"),
        ),
        Demo(
            "evolving-cosmic-mural-prototype",
            "evolving-cosmic-mural-prototype",
            "EvolvingCosmicMural",
            "A cosmic mural that evolves stroke by stroke under MIDI control.",
            _req("midi", "image-gen", "renderer"),
        ),
        Demo(
            "generative-poetry-mosaic",
            "generative-poetry-mosaic",
            "GenerativePoetryMosaic",
            "Speak a theme; poem fragments and imagery tile themselves into a mosaic.",
            _req("mic", "llm", "image-gen", "renderer"),
        ),
        Demo(
            "interactive-storytelling-canvas-prototype",
            "interactive-storytelling-canvas-prototype",
            "InteractiveStorytellingCanvas",
            "A story canvas that grows with each spoken contribution.",
            _req("mic", "llm", "renderer"),
        ),
        Demo(
            "interactive-storytelling",
            "interactive_storytelling",
            "InteractiveStoryteller",
            "Core interactive storytelling experience: speech in, AI narrative out.",
            _req("mic", "llm"),
        ),
        Demo(
            "neural-transfer-music-visualizer",
            "neural-transfer-music-visualizer",
            "NeuralTransferMusicVisualizer",
            "Style-transfer visuals driven by a music track and your camera.",
            _req(
                "audio-out",
                "camera",
                "image-gen",
                "renderer",
                "assets",
            ),
            assets=("your_music_track.mp3",),
        ),
        Demo(
            "real-time-glitch-art-lab",
            "real-time-glitch-art-lab",
            "RealTimeGlitchArtLab",
            "Streams live camera frames through a glitch corruption pipeline.",
            _req("camera", "renderer", optional=("llm",)),
        ),
        Demo(
            "sentiment-analysis-display",
            "sentiment_analysis_display",
            "SentimentDisplay",
            "Listens to visitors and renders the room's sentiment as living imagery.",
            _req(
                "mic",
                "llm",
                "image-gen",
                "audio-out",
                "renderer",
            ),
        ),
        Demo(
            "speech-activated-art",
            "speech_activated_art",
            "SpeechArtGenerator",
            "Speak, and the wall paints what it heard.",
            _req("mic", "llm", "image-gen", "renderer"),
        ),
        Demo(
            "temporal-art-gallery-prototype",
            "temporal-art-gallery-prototype",
            "TemporalArtGallery",
            "A gallery whose exhibits regenerate as time passes.",
            _req("image-gen", "renderer"),
        ),
        Demo(
            "time-shifted-echo-chamber",
            "time-shifted-echo-chamber",
            "TimeShiftedEchoChamber",
            "Records ambient sound and plays it back time-shifted into layered echoes.",
            _req("mic", "audio-out"),
        ),
        Demo(
            "virtual-cloud-chamber",
            "virtual-cloud-chamber",
            "VirtualCloudChamber",
            "2D particle-track cloud chamber with AI narration.",
            _req(
                "renderer",
                "audio-out",
                optional=("llm", "mic", "afterwords"),
            ),
        ),
        Demo(
            "virtual-time-travel",
            "virtual_time_travel",
            "TimeTravelExperience",
            "MIDI time machine: dial an era, see and hear it re-imagined.",
            _req(
                "midi",
                "image-gen",
                "renderer",
                optional=("afterwords",),
            ),
        ),
        Demo(
            "whispers",
            "whispers",
            "Whispers",
            "Overheard fragments return as generated whispers drifting through the space.",
            _req(
                "mic",
                "camera",
                "audio-out",
                "renderer",
                optional=("afterwords",),
            ),
        ),
    ]
}
