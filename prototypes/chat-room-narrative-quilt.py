import lunar_tools as lt
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import numpy as np
# from flask import Flask, render_template
# from flask_socketio import SocketIO, emit
from src.lunar_tools_art import Manager

class ChatRoomNarrativeQuilt:
    def __init__(self, lunar_tools_art_manager: LunarToolsArtManager, flask_app=None, socketio=None, font_path="arial.ttf", font_size=15):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.dalle3 = self.l.lunar_tools_art_manager.dalle3
        self.renderer = self.lunar_tools_art_manager.renderer
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.quilt_image = Image.new('RGB', (self.renderer.width, self.renderer.height), color = (200, 200, 200)) # Light gray canvas
        self.patch_size = (300, 200) # Width, Height for each patch
        self.grid_cols = self.renderer.width // self.patch_size[0]
        self.grid_rows = self.renderer.height // self.patch_size[1]
        self.patches = []
        self.flask_app = flask_app
        self.socketio = socketio
        self.font_path = font_path
        self.font_size = font_size

        if self.flask_app and self.socketio:
            self._setup_flask_routes()

    def _setup_flask_routes(self):
        @self.flask_app.route('/')
        def index():
            # return render_template('index.html') # Requires an index.html template
            return "<h1>Chat Room Narrative Quilt</h1><p>Connect via WebSocket to send messages.</p>"

        @self.socketio.on('message')
        def handle_message(msg):
            self.logger.info(f"Received message: {msg}")
            self._process_chat_message(msg)
            # Emit updated quilt image to all clients (in a real app, you'd send image data or URL)
            # For now, just print a confirmation
            emit('quilt_update', {'status': 'updated'}, broadcast=True)

    def _craft_patch_description(self, chat_message):
        prompt = f"Given the chat message: \"{chat_message}\". Craft a short, evocative description for a visual \"patch\" in a narrative quilt. Focus on imagery and mood. Max 20 words."
        description = self.gpt4.generate(prompt)
        return description.strip()

    def _generate_panel_graphic(self, description):
        prompt = f"Generate a small abstract panel graphic based on: {description}"
        try:
            image, _ = self.dalle3.generate(prompt, image_size="square_small")
            return image
        except Exception as e:
            self.logger.error(f"Error generating panel graphic for '{description}': {e}", exc_info=True)
            return Image.new('RGB', (self.patch_size[0], self.patch_size[1]), color = (100, 100, 100)) # Placeholder

    def _composite_patch(self, panel_graphic, message):
        patch_img = panel_graphic.resize(self.patch_size)
        draw = ImageDraw.Draw(patch_img)
        
        try:
            font = ImageFont.truetype(self.font_path, self.font_size)
        except IOError:
            self.logger.warning(f"Font not found at {self.font_path}. Using default font.")
            font = ImageFont.load_default()

        text_color = (0, 0, 0) # Black text
        
        # Add message to the patch
        wrapper = textwrap.TextWrapper(width=int(self.patch_size[0] / (self.font_size * 0.6))) # Estimate chars per line
        wrapped_message = wrapper.fill(text=message)
        draw.text((5, 5), wrapped_message, font=font, fill=text_color)
        
        return patch_img

    def _add_patch_to_quilt(self, patch_img):
        num_patches = len(self.patches)
        row = num_patches // self.grid_cols
        col = num_patches % self.grid_cols

        if row >= self.grid_rows:
            self.logger.info("Quilt full, starting new row/clearing quilt.")
            # Option to clear quilt or start a new row/page
            self.quilt_image = Image.new('RGB', (self.renderer.width, self.renderer.height), color = (200, 200, 200))
            self.patches = []
            row = 0
            col = 0

        x_offset = col * self.patch_size[0]
        y_offset = row * self.patch_size[1]
        self.quilt_image.paste(patch_img, (x_offset, y_offset))
        self.patches.append(patch_img) # Keep track of patches

    def _process_chat_message(self, message):
        self.logger.info(f"Processing chat message: {message}")
        patch_description = self._craft_patch_description(message)
        panel_graphic = self._generate_panel_graphic(patch_description)
        patch = self._composite_patch(panel_graphic, message)
        self._add_patch_to_quilt(patch)
        self.renderer.render(np.array(self.quilt_image))

    def run(self):
        self.logger.info("Chat Room Narrative Quilt: Press 'q' to quit.")
        if self.flask_app and self.socketio:
            self.logger.info("Flask server and Socket.IO enabled. Access via web browser.")
            # self.socketio.run(self.flask_app, host='0.0.0.0', port=5000) # This would block
            # For a non-blocking run, you'd typically run Flask/SocketIO in a separate thread
            # or use an async framework. For this prototype, we'll simulate message input.
        else:
            self.logger.info("Flask and Socket.IO not configured. Using keyboard input for messages.")

        while True:
            if self.keyboard_input.is_key_pressed('q'):
                self.logger.info("Exiting Chat Room Narrative Quilt.")
                break

            if not (self.flask_app and self.socketio):
                # Simulate chat messages via keyboard input if Flask/SocketIO not used
                message = input("Enter chat message (or 'q' to quit): ")
                if message.lower() == 'q':
                    self.logger.info("Exiting Chat Room Narrative Quilt.")
                    break
                if message:
                    self._process_chat_message(message)

            time.sleep(0.1) # Small delay

if __name__ == "__main__":
    # Example of how to run with Flask and Socket.IO (requires installation of flask and flask-socketio)
    # from flask import Flask
    # from flask_socketio import SocketIO
    # app = Flask(__name__)
    # socketio = SocketIO(app)
    # quilt = ChatRoomNarrativeQuilt(flask_app=app, socketio=socketio)
    # # To run the Flask app, you'd typically use app.run() or socketio.run(app)
    # # For this example, we'll just run the quilt's main loop for keyboard input.
    # quilt.run()

    # Running without Flask/Socket.IO (keyboard input only)
    quilt = ChatRoomNarrativeQuilt()
    quilt.run()
