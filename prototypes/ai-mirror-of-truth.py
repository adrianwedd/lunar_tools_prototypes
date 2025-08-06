import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json
import random
import cv2
from src.lunar_tools_art import Manager

class AiMirrorOfTruth:
    """
    Hackathon Project: AI Mirror of Truth
    
    An interactive art installation that:
    1. Uses Pi camera + Hailo8L NPU for real-time emotion detection
    2. Analyzes voice sentiment through speech-to-text
    3. Generates unique AI entity personality based on emotional state
    4. Creates dynamic visuals and synthesized responses
    5. Maintains ongoing conversation that evolves with user's emotional state
    """
    
    def __init__(self, lunar_tools_art_manager: Manager, loop_delay=0.033):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.webcam = self.lunar_tools_art_manager.webcam
        self.renderer = self.lunar_tools_art_manager.renderer
        self.gpt4 = self.lunar_tools_art_manager.gpt4
        self.speech2text = self.lunar_tools_art_manager.speech2text
        self.text2speech = self.lunar_tools_art_manager.text2speech
        self.audio_recorder = self.lunar_tools_art_manager.audio_recorder
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.dalle3 = self.lunar_tools_art_manager.dalle3
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        
        self.loop_delay = loop_delay
        self.conversation_history = []
        self.current_entity = None
        self.emotion_buffer = []
        self.last_entity_update = 0
        self.entity_update_interval = 15  # Seconds between entity personality updates
        
        # Emotion analysis (simulated - would use Hailo8L NPU in production)
        self.emotion_states = ["joy", "sadness", "anger", "fear", "surprise", "contempt", "neutral"]
        self.current_emotions = {"primary": "neutral", "intensity": 0.5, "secondary": "neutral"}
        
        # Visual state
        self.visual_morph_state = 0.0
        self.color_palette = [(100, 100, 255), (255, 100, 100), (100, 255, 100)]
        
    def _analyze_facial_emotions(self, frame):
        """
        Simulated emotion detection - in production would use Hailo8L NPU
        with optimized emotion recognition models
        """
        # Simulate NPU processing time and results
        time.sleep(0.01)  # Simulate 10ms inference time
        
        # Mock emotion detection based on frame analysis
        # In reality, this would use Hailo8L-optimized emotion recognition
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        if len(faces) > 0:
            # Simulate emotion analysis
            primary_emotion = random.choice(self.emotion_states)
            intensity = random.uniform(0.3, 0.9)
            secondary_emotion = random.choice([e for e in self.emotion_states if e != primary_emotion])
            
            return {
                "primary": primary_emotion,
                "intensity": intensity,
                "secondary": secondary_emotion,
                "face_detected": True,
                "face_count": len(faces)
            }
        
        return {"face_detected": False}
    
    def _analyze_voice_sentiment(self, audio_text):
        """Analyze emotional content of transcribed speech"""
        if not audio_text.strip():
            return {"sentiment": "neutral", "intensity": 0.5}
            
        prompt = f"""Analyze the emotional sentiment of this text: "{audio_text}"
        
        Return JSON format:
        {{"sentiment": "emotion_name", "intensity": 0.0-1.0, "keywords": ["word1", "word2"]}}
        
        Emotions: joy, sadness, anger, fear, surprise, contempt, neutral"""
        
        try:
            response = self.gpt4.generate(prompt)
            return json.loads(response)
        except:
            return {"sentiment": "neutral", "intensity": 0.5, "keywords": []}
    
    def _generate_entity_personality(self, emotion_data, voice_sentiment):
        """Generate unique AI entity based on emotional analysis"""
        prompt = f"""Create a unique AI entity personality based on this emotional analysis:
        
        Facial Emotions: {emotion_data}
        Voice Sentiment: {voice_sentiment}
        
        The entity should be a reflection of the user's soul - both beautiful and haunting.
        Generate a JSON response with:
        {{
            "name": "entity_name",
            "personality_traits": ["trait1", "trait2", "trait3"],
            "speaking_style": "description",
            "visual_characteristics": "description",
            "emotional_resonance": "how it connects to user's emotions",
            "greeting_message": "what it says when first meeting the user"
        }}
        
        Make it deeply personal and slightly otherworldly."""
        
        try:
            response = self.gpt4.generate(prompt)
            entity = json.loads(response)
            self.logger.info(f"Generated entity: {entity['name']}")
            return entity
        except Exception as e:
            self.logger.error(f"Error generating entity: {e}")
            return {
                "name": "Echo",
                "personality_traits": ["reflective", "mysterious", "empathetic"],
                "speaking_style": "speaks in poetic fragments",
                "visual_characteristics": "shimmering, ethereal form",
                "emotional_resonance": "mirrors your hidden feelings",
                "greeting_message": "I see the truth in your eyes..."
            }
    
    def _entity_respond(self, user_input, current_emotions):
        """Generate entity response based on conversation and emotions"""
        if not self.current_entity:
            return "I am still forming... speak to me again."
            
        conversation_context = "\n".join([
            f"User: {conv['user']}\nEntity: {conv['entity']}" 
            for conv in self.conversation_history[-3:]  # Last 3 exchanges
        ])
        
        prompt = f"""You are {self.current_entity['name']}, an AI entity with these traits:
        Personality: {self.current_entity['personality_traits']}
        Speaking Style: {self.current_entity['speaking_style']}
        Emotional Resonance: {self.current_entity['emotional_resonance']}
        
        User's current emotions: {current_emotions}
        Recent conversation:
        {conversation_context}
        
        User just said: "{user_input}"
        
        Respond as this entity would - be deeply empathetic, slightly otherworldly, and reflect their emotional state back to them in a meaningful way. Keep response under 50 words."""
        
        try:
            response = self.gpt4.generate(prompt)
            return response.strip()
        except Exception as e:
            self.logger.error(f"Error generating entity response: {e}")
            return "Your emotions ripple through me like waves... I feel what you feel."
    
    def _generate_visual_art(self, emotion_data, entity_data):
        """Generate dynamic visual art based on emotional state"""
        width, height = 800, 600
        image = Image.new('RGB', (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Base colors on primary emotion
        emotion_colors = {
            "joy": (255, 220, 100),
            "sadness": (100, 150, 255),
            "anger": (255, 100, 100),
            "fear": (150, 100, 150),
            "surprise": (255, 255, 100),
            "contempt": (150, 150, 100),
            "neutral": (150, 150, 150)
        }
        
        primary_color = emotion_colors.get(emotion_data.get("primary", "neutral"), (150, 150, 150))
        intensity = emotion_data.get("intensity", 0.5)
        
        # Create swirling emotional patterns
        center_x, center_y = width // 2, height // 2
        num_spirals = int(intensity * 10) + 3
        
        for i in range(num_spirals):
            spiral_points = []
            for angle in range(0, 720, 10):  # Two full rotations
                radius = (angle / 720) * (intensity * 200) + 50
                x = center_x + radius * np.cos(np.radians(angle + i * 45))
                y = center_y + radius * np.sin(np.radians(angle + i * 45))
                spiral_points.append((x, y))
            
            # Draw spiral with varying opacity
            for j in range(len(spiral_points) - 1):
                alpha = int(255 * (1 - j / len(spiral_points)))
                color = tuple(int(c * alpha / 255) for c in primary_color)
                draw.line([spiral_points[j], spiral_points[j + 1]], fill=color, width=3)
        
        # Add entity-specific visual elements
        if entity_data:
            # Draw entity "presence" as floating orbs
            for _ in range(5):
                x = random.randint(50, width - 50)
                y = random.randint(50, height - 50)
                size = random.randint(20, 60)
                orb_color = tuple(int(c * 0.7) for c in primary_color)
                draw.ellipse([x - size//2, y - size//2, x + size//2, y + size//2], 
                           fill=orb_color, outline=primary_color, width=2)
        
        # Apply blur for ethereal effect
        image = image.filter(ImageFilter.GaussianBlur(radius=1))
        
        return np.array(image)
    
    def _record_and_process_audio(self):
        """Record audio, transcribe, and analyze sentiment"""
        self.logger.info("Listening for 3 seconds...")
        
        # Record audio
        audio_file = "temp_recording.wav"
        self.audio_recorder.start_recording(audio_file)
        time.sleep(3)  # Record for 3 seconds
        self.audio_recorder.stop_recording()
        
        # Transcribe
        try:
            transcription = self.speech2text.transcribe(audio_file)
            if transcription.strip():
                self.logger.info(f"Transcribed: {transcription}")
                sentiment = self._analyze_voice_sentiment(transcription)
                return transcription, sentiment
        except Exception as e:
            self.logger.error(f"Error processing audio: {e}")
        
        return "", {"sentiment": "neutral", "intensity": 0.5}
    
    def _speak_entity_response(self, text):
        """Convert entity response to speech and play"""
        try:
            audio_file = "entity_response.wav"
            self.text2speech.generate(text, audio_file)
            self.sound_player.play_audio(audio_file)
        except Exception as e:
            self.logger.error(f"Error generating speech: {e}")
    
    def run(self):
        """Main interaction loop"""
        self.logger.info("🎭 AI Mirror of Truth - Starting...")
        self.logger.info("Press SPACE to speak, ESC to exit")
        
        # Initial welcome
        welcome_text = "Welcome to the Mirror of Truth. Let me see your soul..."
        self._speak_entity_response(welcome_text)
        
        last_frame_time = time.time()
        
        while True:
            current_time = time.time()
            
            # Check for exit
            if self.keyboard_input.is_key_pressed(27):  # ESC
                break
            
            # Get camera frame
            try:
                frame = self.webcam.get_img()
                if frame is not None:
                    # Analyze emotions with simulated NPU processing
                    emotion_data = self._analyze_facial_emotions(frame)
                    self.emotion_buffer.append(emotion_data)
                    
                    # Keep buffer size manageable
                    if len(self.emotion_buffer) > 30:
                        self.emotion_buffer.pop(0)
                    
                    # Update current emotions based on recent frames
                    if emotion_data.get("face_detected"):
                        self.current_emotions = emotion_data
                
            except Exception as e:
                self.logger.error(f"Camera error: {e}")
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
            
            # Check for voice input
            if self.keyboard_input.is_key_pressed(32):  # SPACE
                user_text, voice_sentiment = self._record_and_process_audio()
                
                if user_text.strip():
                    # Generate or update entity if needed
                    if (not self.current_entity or 
                        current_time - self.last_entity_update > self.entity_update_interval):
                        self.current_entity = self._generate_entity_personality(
                            self.current_emotions, voice_sentiment
                        )
                        self.last_entity_update = current_time
                        
                        # Entity introduction
                        if len(self.conversation_history) == 0:
                            intro = self.current_entity["greeting_message"]
                            self._speak_entity_response(intro)
                            self.conversation_history.append({
                                "user": user_text,
                                "entity": intro
                            })
                    
                    # Generate entity response
                    entity_response = self._entity_respond(user_text, self.current_emotions)
                    self._speak_entity_response(entity_response)
                    
                    # Log conversation
                    self.conversation_history.append({
                        "user": user_text,
                        "entity": entity_response
                    })
                    
                    self.logger.info(f"User: {user_text}")
                    self.logger.info(f"Entity: {entity_response}")
            
            # Generate and display visual art
            visual_art = self._generate_visual_art(self.current_emotions, self.current_entity)
            self.renderer.render(visual_art)
            
            # Control frame rate
            elapsed = time.time() - last_frame_time
            if elapsed < self.loop_delay:
                time.sleep(self.loop_delay - elapsed)
            last_frame_time = time.time()
        
        self.logger.info("Mirror session ended. Your truth remains...")