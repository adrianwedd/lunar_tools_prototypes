import threading
import time

from src.lunar_tools_art import Manager


class CollaborativeArtServer:
    def __init__(self, lunar_tools_art_manager: Manager, ip="127.0.0.1", port="5556"):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.stable_diffusion = (
            self.lunar_tools_art_manager.sdxl_turbo
        )  # Assuming SDXL_TURBO can be used for image generation
        self.renderer = self.lunar_tools_art_manager.renderer
        self.server = self.lunar_tools_art_manager.zmq_pair_endpoint
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger

        if ip == "127.0.0.1" and port == "5556":
            self.logger.warning(
                "Using default IP and port. Consider configuring specific values."
            )
        self.server.ip = ip  # Configure IP and port
        self.server.port = port
        self.running = True  # Control flag for graceful shutdown

    def generate_and_modify_image(self, prompt):
        try:
            image, _ = self.stable_diffusion.generate(prompt)
            self.renderer.render(image)
            return image
        except Exception as e:
            self.lunar_tools_art_manager.logger.error(
                f"Error generating image: {e}", exc_info=True
            )
            return None

    def handle_client(self):
        while self.running:
            if self.keyboard_input.is_key_pressed("q"):
                self.lunar_tools_art_manager.logger.info("Stopping client handler.")
                self.running = False  # Signal main loop to exit as well
                break
            prompt = self.server.get_messages()
            if prompt:
                image = self.generate_and_modify_image(prompt)
                if image is not None:
                    self.server.send_img(image)

    def run(self):
        self.lunar_tools_art_manager.logger.info(
            "Collaborative Art Server: Press 'q' to quit."
        )
        client_thread = threading.Thread(target=self.handle_client)
        client_thread.start()
        while self.running:
            if self.keyboard_input.is_key_pressed("q"):
                self.lunar_tools_art_manager.logger.info(
                    "Exiting Collaborative Art Server."
                )
                self.running = False
                break
            time.sleep(0.1)  # Small delay to prevent busy-waiting
        client_thread.join()  # Wait for the client handler thread to finish


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    server = CollaborativeArtServer(lunar_tools_art_manager)
    server.run()
