from src.lunar_tools_art import Manager


class InteractiveStoryteller:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        recording_duration=5,
        summary_interval=10,
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.story_history = []
        self.summary_interval = summary_interval  # Summarize every N interactions
        self.interaction_count = 0
        self.recording_duration = (
            recording_duration  # Default recording duration in seconds
        )

    def run(self):
        # Placeholder run method for testing purposes
        pass

    def _summarize_story_history(self):
        if len(self.story_history) > self.summary_interval:
            self.lunar_tools_art_manager.logger.info("Summarizing story history...")
            # Keep the last few interactions verbatim for immediate context
            recent_interactions = self.story_history[-self.summary_interval :]
            history_to_summarize = self.story_history[: -self.summary_interval]

            full_history_to_summarize = "\n".join(history_to_summarize)
            summary_prompt = f"Summarize the following story history concisely, focusing on key plot points, character arcs, and unresolved conflicts, in a way that can be used to continue the narrative:\n\n{full_history_to_summarize}\n\nSummary:"

            try:
                summary = self.lunar_tools_art_manager.gpt4.generate(summary_prompt)
                self.story_history = [f"[SUMMARY]: {summary}"] + recent_interactions
                self.lunar_tools_art_manager.logger.info("Story history summarized.")
            except Exception as e:
                self.lunar_tools_art_manager.logger.error(
                    f"Error during story summarization: {e}", exc_info=True
                )
                self.lunar_tools_art_manager.logger.info(
                    "Failed to summarize story history. Continuing without summarization for this turn."
                )
            # For more robust context management, summarize based on token count rather than interaction count.
            # This is a conceptual implementation; a real token counter (e.g., tiktoken) would be needed.
            MAX_TOKENS = 1000  # Example max tokens for context window
            current_story_tokens = len(
                full_history_to_summarize.split()
            )  # Simplified token count (word count)

            if current_story_tokens > MAX_TOKENS:
                self.lunar_tools_art_manager.logger.info(
                    "Story history exceeding token limit. Summarizing..."
                )
                summary_prompt = f"Summarize the following story history concisely, focusing on key plot points, character arcs, and unresolved conflicts, in a way that can be used to continue the narrative:\n\n{full_history_to_summarize}\n\nSummary:"

                try:
                    summary = self.lunar_tools_art_manager.gpt4.generate(summary_prompt)
                    self.story_history = [f"[SUMMARY]: {summary}"] + recent_interactions
                    self.lunar_tools_art_manager.logger.info(
                        "Story history summarized."
                    )
                except Exception as e:
                    self.lunar_tools_art_manager.logger.error(
                        f"Error during story summarization: {e}", exc_info=True
                    )
                    self.lunar_tools_art_manager.logger.info(
                        "Failed to summarize story history. Continuing without summarization for this turn."
                    )
