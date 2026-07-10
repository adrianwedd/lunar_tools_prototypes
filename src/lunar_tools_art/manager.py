import logging
import os

from . import privacy, tools
from .config import config
from .emotion import EmotionDetector
from .llm_backends import create_backend
from .loop_utils import MainLoopQueue
from .prosody import ProsodyAnalyzer
from .tools.headless import headless_active
from .tools.images import DeprecatedAlias, ImageGenerator
from .tools.tts import Text2Speech
from .tracing import traceable
from .voice_client import VoiceClient


class LunarToolsArtManager:
    def __init__(self):
        self._setup_logging()

        # Thread-safe handoff for background threads to reach the main loop.
        self.main_queue = MainLoopQueue()

        # Initialize tools using configuration
        renderer_config = config.get("renderer", {"width": 1920, "height": 1080})
        self.renderer = self._traceable_tool(
            tools.resolve("Renderer"),
            "Renderer",
            width=renderer_config["width"],
            height=renderer_config["height"],
            methods_to_trace=["render"],
        )

        # LLM: use the new pluggable backend. self.gpt4 is a backwards-compat alias.
        self.gpt4 = None

        self.speech2text = self._traceable_tool(
            tools.resolve("Speech2Text"), "Speech2Text", methods_to_trace=["transcribe"]
        )

        # Voice client for the local Afterwords TTS server (no cloud egress;
        # not privacy-gated). Constructed before text2speech wiring below so
        # the Text2Speech adapter can use it when available.
        try:
            afterwords_config = config.get("afterwords", {})
            server_url = (
                afterwords_config.get("server_url", "http://localhost:7860")
                if afterwords_config
                else "http://localhost:7860"
            )
            self.voice_client = VoiceClient(server_url=server_url)
        except Exception as e:
            self.logger.error(f"Failed to initialize VoiceClient: {e}")
            self.voice_client = None

        # text2speech: prefer the local Afterwords adapter when the voice
        # client is up. Otherwise fall back to the cloud OpenAI TTS tool,
        # which is only constructed when privacy.cloud_allowed() (Task 9
        # replaces the fallback with DeprecatedAlias).
        if self.voice_client is not None:
            self.text2speech = self._traceable_tool(
                Text2Speech,
                "Text2Speech",
                methods_to_trace=["generate"],
                voice_client=self.voice_client,
            )
        elif privacy.cloud_allowed():
            self.text2speech = self._traceable_tool(
                tools.resolve("Text2SpeechOpenAI"),
                "Text2SpeechOpenAI",
                methods_to_trace=["generate"],
            )
        else:
            self.logger.info(
                "privacy.mode is local-only and no VoiceClient available; "
                "skipping Text2SpeechOpenAI construction"
            )
            self.text2speech = None

        self.audio_recorder = self._traceable_tool(
            tools.resolve("AudioRecorder"),
            "AudioRecorder",
            methods_to_trace=["start_recording", "stop_recording"],
        )
        self.sound_player = self._traceable_tool(
            tools.resolve("SoundPlayer"), "SoundPlayer", methods_to_trace=["play_audio"]
        )
        keyboard_kwargs = {}
        renderer_window = getattr(self.renderer, "window", None)
        if renderer_window is not None:
            keyboard_kwargs["window"] = renderer_window
        self.keyboard_input = self._traceable_tool(
            tools.resolve("KeyboardInput"),
            "KeyboardInput",
            methods_to_trace=["is_key_pressed"],
            **keyboard_kwargs,
        )
        self.webcam = self._traceable_tool(
            tools.resolve("WebCam"), "WebCam", methods_to_trace=["get_img"]
        )

        # Unified image generator: local mflux by default, gated cloud
        # backends (openai/replicate). Forced to the deterministic `fake`
        # backend in headless mode so tests/CI never touch mflux or the
        # network. Legacy prototype call sites (SDXL_TURBO,
        # Dalle3ImageGenerator, SDXL_LCM, FluxImageGenerator) are served by
        # DeprecatedAlias wrappers around the same generator, regardless of
        # privacy mode — cloud kwargs simply route to local mflux unless a
        # cloud backend was explicitly configured and allowed.
        image_config = dict(config.get("image", {}))
        if headless_active():
            image_config["backend"] = "fake"
        self.image_gen = self._traceable_tool(
            ImageGenerator,
            "ImageGenerator",
            methods_to_trace=["generate"],
            **image_config,
        )

        if self.image_gen is not None:
            self.dalle3 = DeprecatedAlias(self.image_gen, "Dalle3ImageGenerator")
            self.sdxl_turbo = DeprecatedAlias(self.image_gen, "SDXL_TURBO")
            self.sdxl_lcm = DeprecatedAlias(self.image_gen, "SDXL_LCM")
            self.flux = DeprecatedAlias(self.image_gen, "FluxImageGenerator")
        else:
            self.dalle3 = None
            self.sdxl_turbo = None
            self.sdxl_lcm = None
            self.flux = None
        self.zmq_pair_endpoint = self._traceable_tool(
            tools.resolve("ZMQPairEndpoint"),
            "ZMQPairEndpoint",
            methods_to_trace=["send", "receive"],
        )
        self.midi_input = self._traceable_tool(
            tools.resolve("MidiInput"),
            "MidiInput",
            methods_to_trace=["get_latest_message"],
        )

        # New infrastructure components
        try:
            llm_config = config.get("llm", {})
            self.llm_backend = create_backend(llm_config) if llm_config else None
            # Backwards compat: self.gpt4 aliases self.llm_backend
            self.gpt4 = self.llm_backend
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM backend: {e}")
            self.llm_backend = None

        try:
            self.emotion_detector = EmotionDetector()
        except Exception as e:
            self.logger.error(f"Failed to initialize EmotionDetector: {e}")
            self.emotion_detector = None

        try:
            self.prosody_analyzer = ProsodyAnalyzer()
        except Exception as e:
            self.logger.error(f"Failed to initialize ProsodyAnalyzer: {e}")
            self.prosody_analyzer = None

    @property
    def config(self):
        """Expose the config singleton so prototypes can call
        ``self.manager.config.get(...)`` (used by PrototypeBase.get_config)."""
        return config

    def _setup_logging(self):
        log_level_str = config.get("logging.level", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        log_dir = config.get("logging.dir", "logs")
        os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()],
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("LunarToolsArtManager initialized and logging set up.")

    def _traceable_tool(self, tool_class, tool_name, methods_to_trace=None, **kwargs):
        try:
            # Create an instance of the tool class
            instance = tool_class(**kwargs)
        except TypeError as e:
            self.logger.error(f"Invalid arguments for tool {tool_name}: {e}")
            return None
        except ImportError as e:
            self.logger.error(f"Missing dependencies for tool {tool_name}: {e}")
            return None
        except ValueError as e:
            self.logger.error(f"Invalid configuration for tool {tool_name}: {e}")
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error instantiating tool {tool_name}: {e}", exc_info=True
            )
            return None  # Return None if instantiation fails

        if methods_to_trace is None:
            # Default methods to trace for common AI interaction tools
            if tool_name in [
                "GPT4",
                "Dalle3ImageGenerator",
                "FluxImageGenerator",
                "SDXL_TURBO",
                "SDXL_LCM",
            ]:
                methods_to_trace = ["generate"]
            elif tool_name == "Speech2Text":
                methods_to_trace = ["transcribe"]
            elif tool_name in ("Text2SpeechOpenAI", "Text2Speech"):
                methods_to_trace = ["generate"]
            elif tool_name == "ImageGenerator":
                methods_to_trace = ["generate"]
            elif tool_name == "AudioRecorder":
                methods_to_trace = ["start_recording", "stop_recording"]
            elif tool_name == "SoundPlayer":
                methods_to_trace = ["play_audio"]
            elif tool_name == "Renderer":
                methods_to_trace = ["render"]
            elif tool_name == "WebCam":
                methods_to_trace = ["get_img"]
            elif tool_name == "ZMQPairEndpoint":
                methods_to_trace = ["send", "receive"]
            elif tool_name == "MidiInput":
                methods_to_trace = ["get_latest_message"]
            else:
                methods_to_trace = []  # Do not trace other tools by default

        # Wrap specified methods with @traceable
        for method_name in methods_to_trace:
            try:
                if hasattr(instance, method_name) and callable(
                    getattr(instance, method_name)
                ):
                    original_method = getattr(instance, method_name)
                    setattr(
                        instance,
                        method_name,
                        traceable(name=f"{tool_name}.{method_name}")(original_method),
                    )
                else:
                    self.logger.warning(
                        f"Method {method_name} not found or not callable in {tool_name}. Skipping tracing."
                    )
            except Exception as e:
                self.logger.error(
                    f"Error wrapping method {method_name} for tool {tool_name}: {e}",
                    exc_info=True,
                )
        return instance
