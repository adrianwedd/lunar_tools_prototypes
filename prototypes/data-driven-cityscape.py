import lunar_tools as lt
import time
import requests
import json
import random
from PIL import Image, ImageDraw
import numpy as np

from src.lunar_tools_art import Manager

class DataDrivenCityscape:
    def __init__(self, lunar_tools_art_manager: Manager, city="London"):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.renderer = lunar_tools_art_manager.renderer
        self.gpt4 = lunar_tools_art_manager.gpt4
        self.keyboard_input = lunar_tools_art_manager.keyboard_input
        self.logger = lunar_tools_art_manager.logger
        self.weather_api_key = config.get_or_raise("api_keys.openweathermap")
        self.city = city
        self.last_data_fetch_time = 0
        self.data_fetch_interval = 600 # Fetch data every 10 minutes
        self.canvas_image = Image.new('RGB', (self.renderer.width, self.renderer.height), color = (0, 0, 0)) # Black sky

    def _fetch_weather_data(self):
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather?q={self.city}&appid={self.weather_api_key}&units=metric"
            response = requests.get(url)
            response.raise_for_status() # Raise an exception for HTTP errors
            weather_data = response.json()
            return weather_data
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching weather data: {e}", exc_info=True)
            return None

    def _get_cityscape_commands_from_gpt4(self, data_blob):
        prompt = f"Given the following data blob (weather, market, social media, etc.):\n\n{json.dumps(data_blob, indent=2)}\n\nGenerate concise, high-level design commands for a generative cityscape. For example, 'tall glass spires for bullish markets', 'low, sprawling buildings for calm weather', 'bright, neon lights for high social media activity'. Focus on architectural style, height, lighting, and overall mood. Provide only the commands, no conversational filler."
        self.logger.info("Requesting cityscape commands from GPT-4...")
        try:
            commands = self.gpt4.generate(prompt)
            return commands.strip().split('\n')
        except Exception as e:
            print(f"Error getting cityscape commands from GPT-4: {e}")
            return []

    def _draw_cityscape(self, commands):
        draw = ImageDraw.Draw(self.canvas_image)
        # Clear the canvas for a new cityscape
        draw.rectangle([0, 0, self.renderer.width, self.renderer.height], fill=(0, 0, 0))

        # Simple ground
        ground_height = self.renderer.height // 4
        draw.rectangle([0, self.renderer.height - ground_height, self.renderer.width, self.renderer.height], fill=(50, 50, 50))

        building_base_y = self.renderer.height - ground_height

        for command in commands:
            self.logger.info(f"Interpreting command: {command}")
            if "tall glass spires" in command:
                for _ in range(random.randint(3, 7)):
                    x = random.randint(50, self.renderer.width - 50)
                    height = random.randint(self.renderer.height // 2, building_base_y - 50)
                    width = random.randint(20, 50)
                    draw.rectangle([x, building_base_y - height, x + width, building_base_y], fill=(100, 150, 200))
                    # Add more detailed windows
                    for w_y in range(building_base_y - height + 10, building_base_y - 10, 20):
                        draw.rectangle([x + 5, w_y, x + width - 5, w_y + 10], fill=(200, 220, 255))
                        if random.random() < 0.3: # Add some lit windows
                            draw.rectangle([x + 5, w_y, x + width - 5, w_y + 10], fill=(255, 255, 150))
            elif "low, sprawling buildings" in command:
                for _ in range(random.randint(5, 10)):
                    x = random.randint(50, self.renderer.width - 100)
                    height = random.randint(self.renderer.height // 8, self.renderer.height // 4)
                    width = random.randint(80, 150)
                    draw.rectangle([x, building_base_y - height, x + width, building_base_y], fill=(150, 100, 50))
                    # Add roofs
                    draw.polygon([(x, building_base_y - height), (x + width // 2, building_base_y - height - 20), (x + width, building_base_y - height)], fill=(100, 70, 30))
            elif "bright, neon lights" in command:
                for _ in range(random.randint(10, 30)):
                    x = random.randint(0, self.renderer.width)
                    y = random.randint(building_base_y, self.renderer.height)
                    color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                    draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=color)
                    draw.line([(x, y), (x + random.randint(-10, 10), y + random.randint(-10, 10))], fill=color, width=2) # Add light trails
            elif "stormy seascape" in command:
                # Draw stormy clouds with more variation
                for _ in range(random.randint(5, 15)):
                    x = random.randint(0, self.renderer.width)
                    y = random.randint(0, self.renderer.height // 3)
                    radius = random.randint(50, 200)
                    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(40, 40, 60))
                # Draw rough waves with more detail
                for _ in range(random.randint(10, 30)):
                    start_x = random.randint(0, self.renderer.width)
                    start_y = random.randint(building_base_y, self.renderer.height)
                    end_x = start_x + random.randint(-70, 70)
                    end_y = start_y + random.randint(-20, 20)
                    draw.line([start_x, start_y, end_x, end_y], fill=(0, 0, 120), width=random.randint(1, 4))
                    draw.arc([start_x, start_y - 15, end_x, end_y + 15], 0, 180, fill=(0, 0, 180), width=random.randint(1, 2))
            elif "vibrant, sunny landscape" in command:
                # Draw a sun with rays
                sun_x = random.randint(self.renderer.width // 4, self.renderer.width * 3 // 4)
                sun_y = random.randint(self.renderer.height // 8, self.renderer.height // 4)
                sun_radius = random.randint(30, 70)
                draw.ellipse([sun_x - sun_radius, sun_y - sun_radius, sun_x + sun_radius, sun_y + sun_radius], fill=(255, 255, 0))
                for _ in range(12):
                    angle = random.uniform(0, 2 * np.pi)
                    ray_length = random.randint(sun_radius + 10, sun_radius + 50)
                    draw.line([(sun_x, sun_y), (sun_x + ray_length * np.cos(angle), sun_y + ray_length * np.sin(angle))], fill=(255, 255, 150), width=random.randint(1, 3))
                # Draw more varied flowers and greenery
                for _ in range(random.randint(15, 30)):
                    flower_x = random.randint(0, self.renderer.width)
                    flower_y = random.randint(building_base_y - 60, building_base_y - 10)
                    flower_color = (random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))
                    draw.ellipse([flower_x - 5, flower_y - 5, flower_x + 5, flower_y + 5], fill=flower_color)
                    draw.ellipse([flower_x - 2, flower_y - 2, flower_x + 2, flower_y + 2], fill=(255, 255, 0))
                for _ in range(random.randint(5, 10)): # Add some trees
                    tree_x = random.randint(0, self.renderer.width)
                    tree_base_y = random.randint(building_base_y - 40, building_base_y)
                    tree_height = random.randint(30, 80)
                    draw.rectangle([tree_x - 5, tree_base_y - tree_height, tree_x + 5, tree_base_y], fill=(100, 70, 30)) # Trunk
                    draw.ellipse([tree_x - 20, tree_base_y - tree_height - 10, tree_x + 20, tree_base_y - tree_height + 20], fill=(50, 150, 50)) # Leaves
            # Add more command interpretations here

    def run(self):
        self.logger.info("Data-Driven Cityscape: Press 'q' to quit.")
        while True:
            if self.keyboard_input.is_key_pressed('q'):
                self.logger.info("Exiting Data-Driven Cityscape.")
                break

            current_time = time.time()
            if current_time - self.last_data_fetch_time > self.data_fetch_interval:
                self.logger.info("Fetching new data...")
                weather_data = self._fetch_weather_data()
                # Simulate market and social media data for demonstration
                market_data = {"stock_index": random.uniform(1000, 5000), "trend": random.choice(["bullish", "bearish", "stable"])}
                social_media_data = {"sentiment": random.choice(["positive", "negative", "neutral"]), "activity_level": random.uniform(0, 100)}
                
                data_blob = {
                    "weather": weather_data,
                    "market": market_data, # Placeholder for actual market data API call
                    "social_media": social_media_data # Placeholder for actual social media data API call
                }
                
                if weather_data:
                    commands = self._get_cityscape_commands_from_gpt4(data_blob)
                    self._draw_cityscape(commands)
                    self.last_data_fetch_time = current_time
                else:
                    self.logger.warning("Skipping cityscape update due to data fetch error.")

            # Animate subtle details (e.g., blinking lights, drifting clouds)
            # This would involve modifying self.canvas_image slightly each frame
            # For now, we just re-render the static image.
            self.renderer.render(np.array(self.canvas_image))

            time.sleep(0.1) # Small delay for continuous rendering

if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    cityscape = DataDrivenCityscape(lunar_tools_art_manager)
    cityscape.run()
