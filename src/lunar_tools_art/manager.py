from .tools import AudioRecorder, Dalle3ImageGenerator, FluxImageGenerator, GPT4, KeyboardInput, MidiInput, Ollama, Renderer, SDXL_LCM, SDXL_TURBO, SoundPlayer, Speech2Text, Text2SpeechOpenAI, WebCam, ZMQPairEndpoint
import logging
import os
from datetime import datetime
from langsmith import traceable
from .config import config, MissingConfigError

class LunarToolsArtManager:
    def __init__(self):
        self._setup_logging()

        # Initialize tools using configuration
        renderer_config = config.get("renderer", {"width": 1920, "height": 1080})
        self.renderer = self._traceable_tool(Renderer, "Renderer", width=renderer_config["width"], height=renderer_config["height"], methods_to_trace=["render"])

        llm_provider = config.get("llm.provider", "gpt4")

        if llm_provider == "gpt4":
            self.gpt4 = self._traceable_tool(GPT4, "GPT4", methods_to_trace=["generate"])
        elif llm_provider == "ollama":
            ollama_model = config.get("llm.ollama.model", "deepseek-r1:1.5b")
            self.gpt4 = self._traceable_tool(Ollama, "Ollama", model=ollama_model, methods_to_trace=["generate"])
        else:
            self.logger.warning(f"Unknown LLM provider: {llm_provider}. Defaulting to GPT4.")
            self.gpt4 = self._traceable_tool(GPT4, "GPT4", methods_to_trace=["generate"])

        self.speech2text = self._traceable_tool(Speech2Text, "Speech2Text", methods_to_trace=["transcribe"])
        self.text2speech = self._traceable_tool(Text2SpeechOpenAI, "Text2SpeechOpenAI", methods_to_trace=["generate"])
        self.audio_recorder = self._traceable_tool(AudioRecorder, "AudioRecorder", methods_to_trace=["start_recording", "stop_recording"])
        self.sound_player = self._traceable_tool(SoundPlayer, "SoundPlayer", methods_to_trace=["play_audio"])
        self.keyboard_input = self._traceable_tool(KeyboardInput, "KeyboardInput", methods_to_trace=["is_key_pressed"])
        self.webcam = self._traceable_tool(WebCam, "WebCam", methods_to_trace=["get_img"])
        self.sdxl_turbo = self._traceable_tool(SDXL_TURBO, "SDXL_TURBO", methods_to_trace=["generate"])
        self.dalle3 = self._traceable_tool(Dalle3ImageGenerator, "Dalle3ImageGenerator", methods_to_trace=["generate"])
        self.flux = self._traceable_tool(FluxImageGenerator, "FluxImageGenerator", methods_to_trace=["generate"])
        self.sdxl_lcm = self._traceable_tool(SDXL_LCM, "SDXL_LCM", methods_to_trace=["generate"])
        self.zmq_pair_endpoint = self._traceable_tool(ZMQPairEndpoint, "ZMQPairEndpoint", methods_to_trace=["send", "receive"])
        self.midi_input = self._traceable_tool(MidiInput, "MidiInput", methods_to_trace=["get_latest_message"])

    def _setup_logging(self):
        log_level_str = config.get("logging.level", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        log_dir = config.get("logging.dir", "logs")
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"lunar_tools_art_{timestamp}.log")

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("LunarToolsArtManager initialized and logging set up.")

    def _traceable_tool(self, tool_class, tool_name, methods_to_trace=None, **kwargs):
        try:
            # Create an instance of the tool class
            instance = tool_class(**kwargs)
        except Exception as e:
            self.logger.error(f"Error instantiating tool {tool_name}: {e}", exc_info=True)
            return None # Return None if instantiation fails

        if methods_to_trace is None:
            # Default methods to trace for common AI interaction tools
            if tool_name in ["GPT4", "Dalle3ImageGenerator", "FluxImageGenerator", "SDXL_TURBO", "SDXL_LCM"]:
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
                methods_to_trace = [] # Do not trace other tools by default

        # Wrap specified methods with @traceable
        for method_name in methods_to_trace:
            try:
                if hasattr(instance, method_name) and callable(getattr(instance, method_name)):
                    original_method = getattr(instance, method_name)
                    setattr(instance, method_name, traceable(name=f"{tool_name}.{method_name}")(original_method))
                else:
                    self.logger.warning(f"Method {method_name} not found or not callable in {tool_name}. Skipping tracing.")
            except Exception as e:
                self.logger.error(f"Error wrapping method {method_name} for tool {tool_name}: {e}", exc_info=True)
        return instance
