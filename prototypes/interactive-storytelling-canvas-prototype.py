import time

from utils import record_and_transcribe_speech


class InteractiveStorytellingCanvas:
    def __init__(
        self,
        lunar_tools_art_manager,
        loop_delay=2,
        glif_id="clgh1vxtu0011mo081dplq3xs",
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.renderer = self.lunar_tools_art_manager.renderer
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.llm = self.lunar_tools_art_manager.gpt4
        self.glif_api = self.lunar_tools_art_manager.glif_api
        self.logger = self.lunar_tools_art_manager.logger
        self.story = ""  # For very long stories, consider implementing summarization to avoid GPT-4 context window limits.
        self.glif_id = glif_id  # Configurable Glif ID for story visualization
        self.loop_delay = loop_delay

    def get_user_input(self):
        self.logger.info("Tell me what happens next in the story...")
        user_input = record_and_transcribe_speech(self.speech2text, duration=10)
        return user_input

    def generate_story_continuation(self, user_input):
        try:
            prompt = f"Given the current story: '{self.story}', and the user's input: '{user_input}', continue the story in a creative and coherent way."
            continuation = self.llm.generate(prompt)
            self.story += " " + continuation
            return continuation
        except Exception as e:
            self.logger.error(
                f"Error generating story continuation: {e}", exc_info=True
            )
            return None

    def visualize_story(self):
        try:
            inputs = {"node_6": self.story}  # Adjust node name as per your Glif setup
            result = self.lunar_tools_manager.glif_api.run_glif(self.glif_id, inputs)
            if "image" in result:
                return result["image"]
            else:
                self.logger.error(
                    "Failed to generate image:", result.get("error", "Unknown error")
                )
                return None
        except Exception as e:
            self.logger.error(f"Error visualizing story: {e}", exc_info=True)
            return None

    def run(self):
        while True:
            try:
                user_input = self.get_user_input()
                if user_input:
                    self.logger.info(f"You said: {user_input}")
                    continuation = self.generate_story_continuation(user_input)

                    if continuation:
                        self.logger.info(f"Story continuation: {continuation}")
                        image = self.visualize_story()
                        if image:
                            self.renderer.render(image)
                else:
                    self.logger.info("No input detected. Please try again.")
            except Exception as e:
                self.logger.error(f"An error occurred: {e}", exc_info=True)
                self.logger.info("Continuing to next iteration...")

            time.sleep(self.loop_delay)  # Short pause before next iteration


if __name__ == "__main__":
    from src.lunar_tools_art.manager import Manager

    lunar_tools_art_manager = Manager()
    canvas = InteractiveStorytellingCanvas(lunar_tools_art_manager)
    canvas.run()
