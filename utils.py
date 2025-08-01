import datetime
import logging
import time

from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file


def record_and_transcribe_speech(speech2text_instance, duration=3):
    """Records speech for a given duration and transcribes it."""
    logging.info("Listening...")
    transcription = speech2text_instance.transcribe(duration=duration)
    logging.info(f"Transcribed: {transcription}")
    return transcription


def generate_and_play_speech(
    text2speech_instance, sound_player_instance, text, filename=None
):
    """Generates speech from text and plays it."""
    if filename is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f".output/output_speech_{timestamp}.mp3"

    logging.info(f"Generating speech for: {text[:50]}...")
    text2speech_instance.generate(text, filename)
    sound_player_instance.play_sound(filename)
    logging.info("Speech playback complete.")
    return filename


def save_response_to_file(response, prefix):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f".output/{prefix}_{timestamp}.txt"
    with open(filename, "w") as f:
        f.write(response)
    logging.info(f"Saved response to {filename}")
    return filename


def run_until_quit(callback, manager, fps=60):
    while True:
        if manager.keyboard_input.is_key_pressed("q"):
            manager.logger.info("Exiting application.")
            break
        callback()
        time.sleep(1 / fps)
