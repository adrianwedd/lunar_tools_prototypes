import time

from src.lunar_tools_art import Manager


class EscapeRoomGame:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        correct_answer_sound="correct_answer.mp3",
        hint_sound="hint.mp3",
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.renderer = self.lunar_tools_art_manager.renderer
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.correct_answer_sound = correct_answer_sound
        self.hint_sound = hint_sound
        self.game_state = {
            "current_puzzle": 0,
            "puzzles_solved": [],
            "inventory": [],
            "game_over": False,
        }
        self.puzzles = [
            {
                "description": "a locked wooden chest with strange symbols",
                "solution": "open chest",
            },
            {
                "description": "a dimly lit corridor with a flickering light",
                "solution": "go forward",
            },
            {
                "description": "a complex ancient mechanism with missing gears",
                "solution": "fix mechanism",
            },
        ]

    def generate_next_puzzle_visual(self):
        if self.game_state["current_puzzle"] < len(self.puzzles):
            puzzle_description = self.puzzles[self.game_state["current_puzzle"]][
                "description"
            ]
            prompt = f"A visual representation of a puzzle: {puzzle_description}. Style: intricate, mysterious, ancient, high detail."
            try:
                image, _ = self.lunar_tools_art_manager.dalle3.generate(prompt)
                return image
            except Exception as e:
                self.lunar_tools_art_manager.logger.error(
                    f"Error generating puzzle visual for '{puzzle_description}': {e}",
                    exc_info=True,
                )
                return None  # Return None or a default image on error
        else:
            self.logger.info("All puzzles solved. Generating game over visual.")
            prompt = "A visual representing the successful completion of an escape room. Style: triumphant, celebratory, detailed."
            try:
                image, _ = self.lunar_tools_art_manager.dalle3.generate(prompt)
                return image
            except Exception as e:
                self.lunar_tools_art_manager.logger.error(
                    f"Error generating game over visual: {e}", exc_info=True
                )
                return None

    def run(self):
        self.logger.info("Escape Room Game: Press 'q' to quit.")

        # Initial puzzle display
        if self.game_state["current_puzzle"] < len(self.puzzles):
            initial_image = self.generate_next_puzzle_visual()
            self.renderer.render(initial_image)
            self.logger.info(
                f"Current puzzle: {self.puzzles[self.game_state['current_puzzle']]['description']}"
            )
        else:
            self.logger.info("No puzzles defined or game already completed.")
            return

        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Escape Room Game.")
                break

            command = self.speech2text.transcribe(duration=5)
            self.logger.info(f"Transcribed command: {command}")

            if command:
                intent_prompt = f"Analyze the following user command and determine their intent. Respond with 'solve_puzzle', 'get_hint', or 'unknown'. Command: '{command}'"
                intent = (
                    self.lunar_tools_art_manager.gpt4.generate(intent_prompt)
                    .strip()
                    .lower()
                )
                self.logger.info(f"Detected intent: {intent}")

                if intent == "solve_puzzle":
                    current_puzzle_solution = self.puzzles[
                        self.game_state["current_puzzle"]
                    ]["solution"]
                    if current_puzzle_solution.lower() in command.lower():
                        self.logger.info("Puzzle solved!")
                        self.sound_player.play_sound(self.correct_answer_sound)
                        self.game_state["puzzles_solved"].append(
                            self.puzzles[self.game_state["current_puzzle"]]
                        )
                        self.game_state["current_puzzle"] += 1

                        if self.game_state["current_puzzle"] < len(self.puzzles):
                            self.logger.info(
                                f"Moving to next puzzle: {self.puzzles[self.game_state['current_puzzle']]['description']}"
                            )
                            image = self.generate_next_puzzle_visual()
                            self.renderer.render(image)
                        else:
                            self.logger.info("All puzzles solved! Game Over!")
                            self.game_state["game_over"] = True
                            image = (
                                self.generate_next_puzzle_visual()
                            )  # Generate game over visual
                            self.renderer.render(image)
                            break  # Exit game loop
                    else:
                        self.logger.info("Incorrect solution.")
                        # Optionally play a wrong answer sound
                elif intent == "get_hint":
                    self.sound_player.play_sound(self.hint_sound)
                else:
                    self.logger.info("Command not recognized.")

            time.sleep(1)


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    game = EscapeRoomGame(lunar_tools_art_manager)
    game.run()
