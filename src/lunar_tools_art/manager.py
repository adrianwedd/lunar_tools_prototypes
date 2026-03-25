import logging
import os

from langsmith import traceable

from .config import config
from .emotion import EmotionDetector
from .llm_backends import create_backend
from .prosody import ProsodyAnalyzer
from .tools import (
    SDXL_LCM,
    SDXL_TURBO,
    AudioRecorder,
    Dalle3ImageGenerator,
    FluxImageGenerator,
    KeyboardInput,
    MidiInput,
    Renderer,
    SoundPlayer,
    Speech2Text,
    Text2SpeechOpenAI,
    WebCam,
    ZMQPairEndpoint,
)
from .voice_client import VoiceClient


class LunarToolsArtManager:
    def __init__(self):
        self._setup_logging()

        # Initialize tools using configuration
        renderer_config = config.get("renderer", {"width": 1920, "height": 1080})
        self.renderer = self._traceable_tool(
            Renderer,
            "Renderer",
            width=renderer_config["width"],
            height=renderer_config["height"],
            methods_to_trace=["render"],
        )

        # LLM: use the new pluggable backend. self.gpt4 is a backwards-compat alias.
        self.gpt4 = None

        self.speech2text = self._traceable_tool(
            Speech2Text, "Speech2Text", methods_to_trace=["transcribe"]
        )
        self.text2speech = self._traceable_tool(
            Text2SpeechOpenAI, "Text2SpeechOpenAI", methods_to_trace=["generate"]
        )
        self.audio_recorder = self._traceable_tool(
            AudioRecorder,
            "AudioRecorder",
            methods_to_trace=["start_recording", "stop_recording"],
        )
        self.sound_player = self._traceable_tool(
            SoundPlayer, "SoundPlayer", methods_to_trace=["play_audio"]
        )
        self.keyboard_input = self._traceable_tool(
            KeyboardInput, "KeyboardInput", methods_to_trace=["is_key_pressed"]
        )
        self.webcam = self._traceable_tool(
            WebCam, "WebCam", methods_to_trace=["get_img"]
        )
        self.sdxl_turbo = self._traceable_tool(
            SDXL_TURBO, "SDXL_TURBO", methods_to_trace=["generate"]
        )
        self.dalle3 = self._traceable_tool(
            Dalle3ImageGenerator, "Dalle3ImageGenerator", methods_to_trace=["generate"]
        )
        self.flux = self._traceable_tool(
            FluxImageGenerator, "FluxImageGenerator", methods_to_trace=["generate"]
        )
        self.sdxl_lcm = self._traceable_tool(
            SDXL_LCM, "SDXL_LCM", methods_to_trace=["generate"]
        )
        self.zmq_pair_endpoint = self._traceable_tool(
            ZMQPairEndpoint, "ZMQPairEndpoint", methods_to_trace=["send", "receive"]
        )
        self.midi_input = self._traceable_tool(
            MidiInput, "MidiInput", methods_to_trace=["get_latest_message"]
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
            elif tool_name == "Text2SpeechOpenAI":
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
