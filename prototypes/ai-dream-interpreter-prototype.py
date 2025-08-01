import time
from utils import record_and_transcribe_speech, generate_and_play_speech
import logging
from opentelemetry import trace
from src.lunar_tools_art import Manager

class AIDreamInterpreter:
    def __init__(self, lunar_tools_art_manager: Manager, loop_delay=2):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.dalle3 = self.lunar_tools_art_manager.dalle3
        self.llm = self.lunar_tools_art_manager.gpt4 # Using gpt4 as the LLM
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.text2speech = self.lunar_tools_art_manager.text2speech
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.renderer = self.lunar_tools_art_manager.renderer
        self.logger = self.lunar_tools_art_manager.logger
        self.loop_delay = loop_delay
        

    def interpret_dream(self, dream_description):
        try:
            # Generate image based on dream description
            image, _ = self.dalle3.generate(f"A surreal dream scene: {dream_description}")
            
            # Generate interpretation using GPT-4
            interpretation = self.llm.generate(f"Interpret this dream: {dream_description}")
            
            return image, interpretation
        except Exception as e:
            self.logger.error(f"Error interpreting dream: {e}", exc_info=True)
            return None, None

    def run(self):
        while True:
            try:
                self.logger.info("Please describe your dream...")
                dream_description = record_and_transcribe_speech(self.speech2text, duration=10)
                
                if dream_description:
                    self.logger.info(f"You described: {dream_description}")
                    image, interpretation = self.interpret_dream(dream_description)
                    
                    if image and interpretation:
                        # Display image
                        self.renderer.render(image)
                        
                        # Play interpretation
                        generate_and_play_speech(self.text2speech, self.sound_player, interpretation)
                        
                        self.logger.info(f"Interpretation: {interpretation}")
                        
                    else:
                        self.logger.info("Could not generate image or interpretation.")
                else:
                    self.logger.info("No dream description detected. Please try again.")
            except KeyboardInterrupt:
                self.logger.info("\nExiting dream interpreter.")
                break
            except Exception as e:
                self.logger.error(f"An error occurred: {e}. Check the log for details.", exc_info=True)
                self.logger.info("Continuing to next iteration...")
            
            time.sleep(self.loop_delay)

if __name__ == "__main__":
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("ai-dream-interpreter-run") as span:
        lunar_tools_art_manager = Manager()
        interpreter = AIDreamInterpreter(lunar_tools_art_manager)
        interpreter.run()
