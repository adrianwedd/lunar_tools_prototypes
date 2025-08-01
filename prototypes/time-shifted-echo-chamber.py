import time
from collections import deque

from pydub import AudioSegment
from pydub.playback import play

from src.lunar_tools_art import Manager


class TimeShiftedEchoChamber:
    def __init__(
        self,
        lunar_tools_art_manager: Manager,
        clip_duration=5,
        buffer_size=3,
        loop_delay=0.1,
    ):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.audio_recorder = self.lunar_tools_art_manager.audio_recorder
        self.sound_player = self.lunar_tools_art_manager.sound_player
        self.keyboard_input = self.lunar_tools_art_manager.keyboard_input
        self.logger = self.lunar_tools_art_manager.logger
        self.clip_duration = clip_duration
        self.audio_buffer = deque(maxlen=buffer_size)  # Circular buffer for audio clips
        self.delay_factor = 1.0  # Multiplier for playback delay
        self.pitch_factor = 1.0  # Multiplier for pitch shift
        self.loop_delay = loop_delay

    def _record_clip(self):
        self.logger.info(f"Recording {self.clip_duration} second clip...")
        file_path = f".output/temp_clip_{int(time.time())}.wav"
        self.audio_recorder.start_recording(file_path)
        # Assuming audio_recorder.stop_recording() is blocking until recording is complete.
        # If not, a wait_for_recording_completion method would be ideal here.
        self.audio_recorder.stop_recording()
        self.logger.info("Recording complete.")
        self.audio_buffer.append(file_path)

    def _process_and_play_clip(self, clip_path):
        self.logger.info(
            f"Processing and playing {clip_path} with delay {self.delay_factor:.1f} and pitch {self.pitch_factor:.1f}..."
        )
        try:
            audio_segment = AudioSegment.from_wav(clip_path)

            # Apply time stretch
            if self.delay_factor != 1.0:
                # pydub's speedup changes both speed and pitch. For time stretch only, more complex resampling is needed.
                # For simplicity in this prototype, we'll use a direct speedup/slowdown.
                audio_segment = audio_segment.speedup(
                    playback_speed=1.0 / self.delay_factor, chunk_size=150, crossfade=25
                )

            # Apply pitch shift
            if self.pitch_factor != 1.0:
                audio_segment = audio_segment.set_frame_rate(
                    int(audio_segment.frame_rate * self.pitch_factor)
                )

            play(audio_segment)  # Play with pydub
        except Exception as e:
            self.logger.error(
                f"Error processing/playing audio clip {clip_path}: {e}", exc_info=True
            )

    def run(self):
        self.logger.info("Time-Shifted Echo Chamber: Press 'q' to quit.")
        self.logger.info(
            "Use 'd' to increase delay, 'D' to decrease. 'p' to increase pitch, 'P' to decrease."
        )

        # Start recording in a separate thread or asynchronously
        # For simplicity in this prototype, we'll do it in the main loop
        # but a more robust solution would use threading or asyncio.

        while True:
            if self.keyboard_input.is_key_pressed("q"):
                self.logger.info("Exiting Time-Shifted Echo Chamber.")
                break

            # Adjust delay and pitch factors with keyboard input
            if self.keyboard_input.is_key_pressed("d"):
                self.delay_factor = min(2.0, self.delay_factor + 0.1)
                self.logger.info(f"Delay Factor: {self.delay_factor:.1f}")
            if self.keyboard_input.is_key_pressed("D"):
                self.delay_factor = max(0.5, self.delay_factor - 0.1)
                self.logger.info(f"Delay Factor: {self.delay_factor:.1f}")
            if self.keyboard_input.is_key_pressed("p"):
                self.pitch_factor = min(2.0, self.pitch_factor + 0.1)
                self.logger.info(f"Pitch Factor: {self.pitch_factor:.1f}")
            if self.keyboard_input.is_key_pressed("P"):
                self.pitch_factor = max(0.5, self.pitch_factor - 0.1)
                self.logger.info(f"Pitch Factor: {self.pitch_factor:.1f}")

            # Record a new clip
            self._record_clip()

            # Schedule overlapping playback of old clips
            for i, clip in enumerate(list(self.audio_buffer)):
                # Play clips with a delay based on their position in the buffer
                # and the delay factor.
                # In a real system, you'd schedule these with a proper audio engine.
                time.sleep(
                    self.clip_duration
                    * self.delay_factor
                    * (i + 1)
                    / self.audio_buffer.maxlen
                )
                self._process_and_play_clip(clip)

            time.sleep(self.loop_delay)  # Small delay to prevent busy-waiting


if __name__ == "__main__":
    lunar_tools_art_manager = Manager()
    echo_chamber = TimeShiftedEchoChamber(lunar_tools_art_manager)
    echo_chamber.run()
