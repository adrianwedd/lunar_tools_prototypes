class Renderer:
    def __init__(self, *args, **kwargs):
        self.width = kwargs.get("width")
        self.height = kwargs.get("height")

    def render(self, *args, **kwargs):
        pass

    def set_size(self, width, height):
        self.width = width
        self.height = height


class Speech2Text:
    def __init__(self, *args, **kwargs):
        pass

    def transcribe(self, *args, **kwargs):
        pass


class Text2SpeechOpenAI:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        pass


class AudioRecorder:
    def __init__(self, *args, **kwargs):
        pass

    def start_recording(self, *args, **kwargs):
        pass

    def stop_recording(self, *args, **kwargs):
        pass


class SoundPlayer:
    def __init__(self, *args, **kwargs):
        pass

    def play_sound(self, *args, **kwargs):
        pass

    def play_audio(self, *args, **kwargs):
        pass


class KeyboardInput:
    def __init__(self, *args, **kwargs):
        pass

    def is_key_pressed(self, *args, **kwargs):
        return False

    def get(self, *args, **kwargs):
        return None


class WebCam:
    def __init__(self, *args, **kwargs):
        pass

    def get_img(self, *args, **kwargs):
        pass


class SDXL_TURBO:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        pass


class Dalle3ImageGenerator:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        pass


class FluxImageGenerator:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        pass


class SDXL_LCM:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        pass


class ZMQPairEndpoint:
    def __init__(self, *args, **kwargs):
        pass

    def send(self, *args, **kwargs):
        pass

    def receive(self, *args, **kwargs):
        pass

    def get_messages(self, *args, **kwargs):
        return None

    def send_img(self, *args, **kwargs):
        pass


class MidiInput:
    def __init__(self, *args, **kwargs):
        pass

    def get_latest_message(self, *args, **kwargs):
        return None

    def get(self, *args, **kwargs):
        return 0.0


class GPT4:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        pass


class Ollama:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *args, **kwargs):
        pass
