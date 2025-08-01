
import time
from datetime import datetime
from src.lunar_tools_art import Manager

class SentimentDisplay:
    def __init__(self, lunar_tools_art_manager: Manager, recording_duration=5):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.audio_recorder = self.lunar_tools_art_manager.audio_recorder
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.renderer = self.lunar_tools_art_manager.renderer
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.recording_duration = recording_duration

    def analyze_sound(self, file_path):
        try:
            # Transcribe the audio file
            transcription = self.lunar_tools_art_manager.speech2text.transcribe(file_path=file_path)
            self.lunar_tools_art_manager.logger.info(f"Transcribed audio for sentiment analysis: {transcription}")

            if transcription:
                # Use GPT-4 for sentiment analysis
                prompt = f"Analyze the sentiment of the following text and respond with a single word: positive, negative, or neutral. Text: '{transcription}'"
                sentiment_response = self.gpt4.generate(prompt)
                sentiment = sentiment_response.strip().lower()
                if sentiment in ["positive", "negative", "neutral"]:
                    return sentiment
                else:
                    self.lunar_tools_art_manager.logger.warning(f"GPT-4 returned an unrecognised sentiment: {sentiment}. Defaulting to 'neutral'.")
                    return "neutral"
            else:
                self.lunar_tools_art_manager.logger.info("No transcription for sentiment analysis. Defaulting to 'neutral'.")
                return "neutral"
        except Exception as e:
            self.lunar_tools_art_manager.logger.error(f"Error during sentiment analysis: {e}", exc_info=True)
            return "neutral" # Default to neutral on error

    def generate_sentiment_visual(self, sentiment):
        prompt_map = {
            "positive": "A vibrant, abstract image with bright, uplifting colors and flowing shapes.",
            "negative": "A dark, abstract image with sharp, jagged shapes and muted, somber colors.",
            "neutral": "A calm, abstract image with balanced colors and smooth, flowing lines."
        }
        prompt = prompt_map.get(sentiment, prompt_map["neutral"])
        try:
            image, _ = self.lunar_tools_art_manager.dalle3.generate(prompt)
            return image
        except Exception as e:
            self.lunar_tools_art_manager.logger.error(f"Error generating visual for sentiment {sentiment}: {e}", exc_info=True)
            return None # Return None or a default image on error

    def generate_sentiment_sound(self, sentiment):
        sound_description_map = {
            "positive": "A cheerful, uplifting melody.",
            "negative": "A dissonant, unsettling soundscape.",
            "neutral": "A calm, ambient tone."
        }
        description = sound_description_map.get(sentiment, sound_description_map["neutral"])
        try:
            # Generate speech from the description
            # The filename will be handled by generate_and_play_speech in utils.py
            return description # Return the description to be used by generate_and_play_speech
        except Exception as e:
            self.lunar_tools_art_manager.logger.error(f"Error generating sound for sentiment {sentiment}: {e}", exc_info=True)
            return None

    def run(self):
        self.lunar_tools_art_manager.logger.info("Sentiment Analysis Display: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed('q'):
                self.lunar_tools_art_manager.logger.info("Exiting Sentiment Analysis Display.")
                break

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_filename = f".output/visitor_input_{timestamp}.mp3"
            self.audio_recorder.start_recording(audio_filename)
            # Assuming audio_recorder.stop_recording() is blocking until recording is complete.
            # If not, a wait_for_recording_completion method would be ideal here.
            self.audio_recorder.stop_recording()
            
            sentiment = self.analyze_sound(audio_filename)
            image = self.generate_sentiment_visual(sentiment)
            self.renderer.render(image)
            
            sound = self.generate_sentiment_sound(sentiment)
            self.sound_player.play_sound(sound)
            
            time.sleep(5)

if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    display = SentimentDisplay(lunar_tools_art_manager)
    display.run()
