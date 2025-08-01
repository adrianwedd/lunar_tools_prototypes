import time
from src.lunar_tools_art import Manager

class SpeechArtGenerator:
    def __init__(self, lunar_tools_art_manager: Manager, no_speech_delay=1, loop_delay=5):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.dalle3 = self.lunar_tools_art_manager.dalle3
        self.renderer = self.lunar_tools_art_manager.renderer
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.no_speech_delay = no_speech_delay
        self.loop_delay = loop_delay

    def run(self):
        self.lunar_tools_art_manager.logger.info("Speech Activated Art: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed('q'):
                self.lunar_tools_art_manager.logger.info("Exiting Speech Activated Art.")
                break

            try:
                # Capture speech
                speech_text = self.speech2text.transcribe(duration=3)
                self.lunar_tools_art_manager.logger.info(f"Captured speech: {speech_text}")
                
                if not speech_text:
                    self.lunar_tools_art_manager.logger.info("No speech detected, trying again.")
                    time.sleep(self.no_speech_delay)
                    continue

                # Generate prompt from speech text
                self.lunar_tools_art_manager.logger.info("Generating prompt from speech...")
                prompt = self.gpt4.generate(f"Create a visual representation of: {speech_text}")
                self.lunar_tools_art_manager.logger.info(f"Generated prompt: {prompt}")

                if not prompt:
                    self.lunar_tools_art_manager.logger.info("Failed to generate prompt, trying again.")
                    time.sleep(self.no_speech_delay)
                    continue
                
                # Generate image from prompt
                self.lunar_tools_art_manager.logger.info("Generating image...")
                image, _ = self.dalle3.generate(prompt)
                
                # Render the generated image
                self.renderer.render(image)
                
            except Exception as e:
                self.lunar_tools_art_manager.logger.error(f"An error occurred: {e}", exc_info=True)
                self.lunar_tools_art_manager.logger.info("Continuing to next iteration...")
            
            # Wait before capturing the next speech input
            time.sleep(self.loop_delay)

if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    generator = SpeechArtGenerator(lunar_tools_art_manager)
    generator.run()
