import threading
import time

import numpy as np
from PIL import Image, ImageDraw

from src.lunar_tools_art import Manager


class CollaborativeCanvas:
    def __init__(self, lunar_tools_art_manager: Manager, ip="127.0.0.1", port="5557"):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.zmq_endpoint = self.lunar_tools_art_manager.zmq_pair_endpoint
        self.renderer = self.lunar_tools_art_manager.renderer
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger

        if ip == "127.0.0.1" and port == "5557":
            self.logger.warning(
                "Using default IP and port. Consider configuring specific values."
            )
        self.zmq_endpoint.ip = ip
        self.zmq_endpoint.port = port
        self.zmq_endpoint.is_server = True
        self.canvas_image = Image.new(
            "RGB", (self.renderer.width, self.renderer.height), color=(255, 255, 255)
        )  # White canvas
        self.last_suggestion_time = time.time()
        self.suggestion_interval = 30  # Seconds between AI suggestions

    def _process_drawing_event(self, event_data):
        # event_data is expected to be a dictionary with keys like 'x', 'y', 'color', 'stroke_width'
        if not isinstance(event_data, dict):
            self.logger.warning("Invalid drawing event data received.")
            return

        x, y = event_data.get("x"), event_data.get("y")
        color = event_data.get("color", (0, 0, 0))  # Default to black
        stroke_width = event_data.get("stroke_width", 5)

        if x is None or y is None:
            self.logger.warning("Missing x or y coordinates in drawing event.")
            return

        draw = ImageDraw.Draw(self.canvas_image)
        # Draw a circle to represent a stroke
        draw.ellipse(
            (x - stroke_width, y - stroke_width, x + stroke_width, y + stroke_width),
            fill=color,
        )

    def _get_ai_suggestion(self):
        prompt = "Suggest a creative brush style or color palette shift for a collaborative digital canvas. Respond concisely, e.g., 'Use broad, sweeping strokes' or 'Shift to a warm, autumnal palette'."
        suggestion = self.gpt4.generate(prompt)
        return suggestion

    def _handle_incoming_messages(self):
        while True:
            try:
                message = self.zmq_endpoint.get_messages()
                if message:
                    if (
                        isinstance(message, dict)
                        and message.get("type") == "drawing_event"
                    ):
                        self._process_drawing_event(message.get("data"))
                    else:
                        self.logger.warning(f"Received unknown message type: {message}")
            except Exception as e:
                self.logger.error(
                    f"Error handling incoming message: {e}", exc_info=True
                )
            time.sleep(0.01)  # Small delay to prevent busy-waiting

    def run(self):
        self.logger.info("Collaborative Canvas: Press 'q' to quit.")
        message_handler_thread = threading.Thread(target=self._handle_incoming_messages)
        message_handler_thread.daemon = (
            True  # Allow main program to exit even if thread is running
        )
        message_handler_thread.start()

        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Collaborative Canvas.")
                break

            # Render the current canvas
            self.renderer.render(np.array(self.canvas_image))

            # Check for AI suggestions
            current_time = time.time()
            if current_time - self.last_suggestion_time > self.suggestion_interval:
                suggestion = self._get_ai_suggestion()
                if suggestion:
                    self.logger.info(f"AI Suggestion: {suggestion}")
                    # In a full implementation, you might broadcast this suggestion
                    # to all connected clients or apply it to the canvas.
                self.last_suggestion_time = current_time

            time.sleep(0.1)  # Main loop delay


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    canvas = CollaborativeCanvas(lunar_tools_art_manager)
    canvas.run()
