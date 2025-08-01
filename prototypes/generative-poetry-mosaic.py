import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.lunar_tools_art import Manager


class GenerativePoetryMosaic:
    def __init__(
        self, lunar_tools_art_manager: Manager, font_path="arial.ttf", font_size=20
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.dalle3 = self.lunar_tools_art_manager.dalle3
        self.renderer = self.lunar_tools_art_manager.renderer
        self.logger = self.lunar_tools_art_manager.logger
        self.tiles = []
        self.tile_size = (300, 200)  # Width, Height for each tile
        self.grid_cols = self.renderer.width // self.tile_size[0]
        self.grid_rows = self.renderer.height // self.tile_size[1]
        self.canvas = Image.new(
            "RGB", (self.renderer.width, self.renderer.height), color=(0, 0, 0)
        )
        self.font_path = font_path
        self.font_size = font_size

    def _generate_poem(self, keyword):
        prompt = f"Generate a two-line poem about: {keyword}"
        poem = self.gpt4.generate(prompt)
        return poem.strip().split("\n")[:2]  # Ensure two lines

    def _generate_background_image(self, poem_line):
        prompt = f"Abstract background image inspired by: {poem_line}"
        image, _ = self.dalle3.generate(prompt, image_size="square_small")
        return image

    def _create_tile(self, poem_lines, background_image):
        tile_img = background_image.resize(self.tile_size)
        draw = ImageDraw.Draw(tile_img)

        # Try to load a font, fallback to default
        try:
            font = ImageFont.truetype(self.font_path, self.font_size)
        except OSError:
            self.logger.warning(
                f"Font not found at {self.font_path}. Using default font."
            )
            font = ImageFont.load_default()

        text_color = (255, 255, 255)  # White text

        # Add poem lines to the tile
        y_text = 10
        for line in poem_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x_text = (self.tile_size[0] - text_width) / 2
            draw.text((x_text, y_text), line, font=font, fill=text_color)
            y_text += text_height + 5

        return tile_img

    def _add_tile_to_canvas(self, tile_img):
        # Find the next available position in the grid
        num_tiles = len(self.tiles)
        row = num_tiles // self.grid_cols
        col = num_tiles % self.grid_cols

        if row >= self.grid_rows:
            self.logger.info("Canvas full, clearing for new mosaic.")
            self.canvas = Image.new(
                "RGB", (self.renderer.width, self.renderer.height), color=(0, 0, 0)
            )
            self.tiles = []
            row = 0
            col = 0

        x_offset = col * self.tile_size[0]
        y_offset = row * self.tile_size[1]
        self.canvas.paste(tile_img, (x_offset, y_offset))
        self.tiles.append(tile_img)  # Keep track of tiles for count

    def run(self):
        self.logger.info(
            "Generative Poetry Mosaic: Type keywords and press Enter. Press 'q' to quit."
        )
        while True:
            keyword = input("Enter keyword: ")
            if keyword.lower() == "q":
                self.logger.info("Exiting Generative Poetry Mosaic.")
                break

            if not keyword:
                self.logger.info("Please enter a keyword.")
                continue

            try:
                poem_lines = self._generate_poem(keyword)
                if not poem_lines:
                    self.logger.info("Could not generate poem. Try another keyword.")
                    continue

                background_image = self._generate_background_image(poem_lines[0])
                if background_image is None:
                    self.logger.info(
                        "Could not generate background image. Try another keyword."
                    )
                    continue

                tile = self._create_tile(poem_lines, background_image)
                self._add_tile_to_canvas(tile)
                self.renderer.render(np.array(self.canvas))

            except Exception as e:
                self.logger.error(f"An error occurred: {e}", exc_info=True)
                self.logger.info("Continuing...")


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    mosaic = GenerativePoetryMosaic(lunar_tools_art_manager)
    mosaic.run()
