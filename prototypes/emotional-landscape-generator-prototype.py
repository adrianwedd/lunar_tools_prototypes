import time
import random
from src.lunar_tools_art import Manager

class EmotionDetector:
    def __init__(self, lunar_tools_art_manager: Manager):
        self.speech2text = lunar_tools_art_manager.speech2text
        self.gpt4 = lunar_tools_art_manager.gpt4
        self.logger = lunar_tools_art_manager.logger

    def detect_emotion(self):
        try:
            self.logger.info("Listening for emotion input...")
            visitor_input = self.speech2text.transcribe(duration=5) # Capture 5 seconds of audio
            if visitor_input:
                self.logger.info(f"Transcribed input: {visitor_input}")
                prompt = f"Analyze the following text for emotion and respond with a single word: happy, sad, angry, calm, or excited. Text: '{visitor_input}'"
                emotion_response = self.gpt4.generate(prompt)
                emotion = emotion_response.strip().lower()
                if emotion in ["happy", "sad", "angry", "calm", "excited"]:
                    return emotion
                else:
                    self.logger.warning(f"GPT-4 returned an unrecognised emotion: {emotion}. Defaulting to 'calm'.")
                    return "calm"
            else:
                self.logger.info("No speech detected for emotion analysis. Defaulting to 'calm'.")
                return "calm"
        except Exception as e:
            self.logger.error(f"Error during emotion detection: {e}", exc_info=True)
            return "calm" # Default to calm on error

class EmotionalLandscapeGenerator:
    def __init__(self, lunar_tools_art_manager: Manager, update_interval=10):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.sdxl_turbo = self.lunar_tools_art_manager.sdxl_turbo
        self.renderer = self.lunar_tools_art_manager.renderer
        self.emotion_detector = EmotionDetector(lunar_tools_art_manager)
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.update_interval = update_interval
        self.emotion_prompts = {
            "happy": "A vibrant, sunny landscape with blooming flowers",
            "sad": "A misty, rainy forest with bare trees",
            "angry": "A stormy seascape with crashing waves",
            "calm": "A serene lake surrounded by mountains at sunset",
            "excited": "A dynamic cityscape with fireworks in the sky"
        }

    def generate_landscape(self, emotion):
        prompt = self.emotion_prompts.get(emotion, "A neutral landscape")
        try:
            image, _ = self.sdxl_turbo.generate(prompt)
            return image
        except Exception as e:
            self.lunar_tools_art_manager.logger.error(f"Error generating image for emotion {emotion}: {e}", exc_info=True)
            return None

    def run(self):
        self.lunar_tools_art_manager.logger.info("Emotional Landscape Generator: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed('q'):
                self.lunar_tools_art_manager.logger.info("Exiting Emotional Landscape Generator.")
                break

            emotion = self.emotion_detector.detect_emotion()
            self.lunar_tools_art_manager.logger.info(f"Detected emotion: {emotion}")
            
            landscape = self.generate_landscape(emotion)
            if landscape is not None:
                self.renderer.render(landscape)
            
            time.sleep(self.update_interval)  # Wait before next detection

if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    generator = EmotionalLandscapeGenerator(lunar_tools_art_manager)
    generator.run()
