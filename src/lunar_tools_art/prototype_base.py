"""Base class for Lunar Tools Art prototypes.

This module provides a standardized base class that all art installation prototypes
should inherit from. It establishes common patterns for initialization, error handling,
lifecycle management, and resource cleanup.
"""

import logging
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Optional

from .exceptions import PrototypeExceptionHandler
from .manager import Manager


class PrototypeBase(ABC):
    """Abstract base class for all Lunar Tools Art prototypes.

    This class provides:
    - Standardized initialization with Manager instance
    - Common configuration handling
    - Consistent logging setup
    - Exception handling patterns
    - Resource cleanup management
    - Graceful shutdown capabilities
    """

    def __init__(
        self, lunar_tools_art_manager: Manager, loop_delay: float = 0.1, **kwargs: Any
    ):
        """Initialize the prototype with manager and configuration.

        Args:
            lunar_tools_art_manager: Manager instance providing access to tools
            loop_delay: Default delay between main loop iterations in seconds
            **kwargs: Additional configuration parameters
        """
        self.manager = lunar_tools_art_manager
        self.loop_delay = loop_delay
        self.config = kwargs

        # Set up logging with the prototype name
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Set up exception handler for consistent error handling
        self.exception_handler = PrototypeExceptionHandler(
            logger=self.logger, prototype_name=self.__class__.__name__
        )

        # Common tool references for convenience
        self.renderer = self.manager.renderer
        self.keyboard_input = self.manager.keyboard_input

        # Track running state for graceful shutdown
        self._running = False
        self._resources_acquired = []

        self.logger.info(f"{self.__class__.__name__} initialized with config: {kwargs}")

    @abstractmethod
    def setup(self) -> None:
        """Set up the prototype - called once before main loop.

        Override this method to:
        - Initialize art-specific parameters
        - Set up visual elements
        - Prepare data structures
        - Validate configuration
        """
        pass

    @abstractmethod
    def update(self) -> None:
        """Update prototype state - called each loop iteration.

        Override this method to:
        - Process user input
        - Update visual elements
        - Handle AI interactions
        - Render current state
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources - called on shutdown.

        Override this method to:
        - Release file handles
        - Close network connections
        - Save state if needed
        - Clean temporary files
        """
        pass

    def should_exit(self) -> bool:
        """Check if prototype should exit.

        Default implementation checks for 'q' or 'esc' key presses.
        Override to customize exit conditions.

        Returns:
            True if prototype should exit, False otherwise
        """
        return (
            self.keyboard_input.is_key_pressed("q")
            or self.keyboard_input.is_key_pressed("esc")
            or not self._running
        )

    def run(self) -> None:
        """Main execution loop with exception handling and cleanup.

        This method:
        1. Calls setup()
        2. Runs the main loop calling update() repeatedly
        3. Handles exceptions gracefully
        4. Ensures cleanup() is called on exit
        """
        self._running = True

        try:
            self.logger.info(
                f"Starting {self.__class__.__name__} - Press 'q' or 'esc' to exit"
            )

            # Set up exception handler context
            with self.exception_handler:
                # Initial setup
                self.setup()

                # Main loop
                while self._running and not self.should_exit():
                    self.update()
                    time.sleep(self.loop_delay)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user (Ctrl+C)")
        except Exception as e:
            self.logger.error(
                f"Unexpected error in {self.__class__.__name__}: {e}", exc_info=True
            )
        finally:
            self._running = False
            try:
                self.cleanup()
                self.logger.info(f"{self.__class__.__name__} shutdown complete")
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}", exc_info=True)

    def stop(self) -> None:
        """Signal the prototype to stop gracefully."""
        self._running = False
        self.logger.info(f"Stop signal sent to {self.__class__.__name__}")

    @contextmanager
    def acquire_resource(self, resource_name: str, acquire_func, release_func):
        """Context manager for tracking and cleaning up resources.

        Args:
            resource_name: Name for logging
            acquire_func: Function to acquire the resource
            release_func: Function to release the resource

        Yields:
            The acquired resource
        """
        resource = None
        try:
            self.logger.debug(f"Acquiring resource: {resource_name}")
            resource = acquire_func()
            self._resources_acquired.append((resource_name, resource, release_func))
            yield resource
        except Exception as e:
            self.logger.error(f"Failed to acquire resource {resource_name}: {e}")
            raise
        finally:
            if resource and release_func:
                try:
                    self.logger.debug(f"Releasing resource: {resource_name}")
                    release_func(resource)
                except Exception as e:
                    self.logger.error(
                        f"Failed to release resource {resource_name}: {e}"
                    )

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value with fallback to manager config.

        Args:
            key: Configuration key (supports dot notation like "llm.provider")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        # First check prototype-specific config
        if key in self.config:
            return self.config[key]

        # Then check manager's global config
        return self.manager.config.get(key, default)

    def validate_config(self, required_keys: list[str]) -> None:
        """Validate that required configuration keys are present.

        Args:
            required_keys: List of required configuration keys

        Raises:
            ValueError: If any required key is missing
        """
        missing_keys = []
        for key in required_keys:
            if self.get_config(key) is None:
                missing_keys.append(key)

        if missing_keys:
            raise ValueError(
                f"Missing required configuration keys for {self.__class__.__name__}: "
                f"{', '.join(missing_keys)}"
            )

    def log_performance(self, operation: str, duration: float) -> None:
        """Log performance metrics for monitoring.

        Args:
            operation: Name of the operation
            duration: Duration in seconds
        """
        self.logger.debug(f"Performance: {operation} took {duration:.3f}s")

        # Log warning for slow operations
        if duration > 1.0:
            self.logger.warning(
                f"Slow operation detected: {operation} took {duration:.3f}s"
            )


class InteractivePrototype(PrototypeBase):
    """Base class for prototypes that require user interaction.

    Extends PrototypeBase with common interactive features:
    - Speech-to-text integration
    - Audio recording management
    - User input handling
    """

    def __init__(self, lunar_tools_art_manager: Manager, **kwargs):
        super().__init__(lunar_tools_art_manager, **kwargs)

        # Interactive tool references
        self.speech2text = self.manager.speech2text
        self.audio_recorder = self.manager.audio_recorder
        self.sound_player = self.manager.sound_player

        self.logger.info("Interactive prototype initialized")

    def get_user_speech(self, timeout: float = 5.0) -> Optional[str]:
        """Capture and transcribe user speech.

        Args:
            timeout: Recording timeout in seconds

        Returns:
            Transcribed text or None if no speech detected
        """
        try:
            self.logger.debug(f"Listening for user speech (timeout: {timeout}s)")

            # Record audio
            audio_data = self.audio_recorder.record(duration=timeout)
            if not audio_data:
                return None

            # Transcribe to text
            text = self.speech2text.transcribe(audio_data)
            if text:
                self.logger.info(f"User said: '{text}'")
                return text.strip()

        except Exception as e:
            self.logger.error(f"Error capturing user speech: {e}")

        return None


class AIPrototype(PrototypeBase):
    """Base class for prototypes that use AI models.

    Extends PrototypeBase with AI-specific features:
    - LLM integration
    - Image generation
    - Error handling for AI services
    """

    def __init__(self, lunar_tools_art_manager: Manager, **kwargs):
        super().__init__(lunar_tools_art_manager, **kwargs)

        # AI tool references
        self.llm = self.manager.gpt4
        self.text2speech = self.manager.text2speech

        # Image generators (may be None if not configured)
        self.dalle = getattr(self.manager, "dalle", None)
        self.sdxl = getattr(self.manager, "sdxl", None)

        self.logger.info("AI prototype initialized")

    def generate_text(self, prompt: str, **kwargs) -> Optional[str]:
        """Generate text using the configured LLM.

        Args:
            prompt: Input prompt for text generation
            **kwargs: Additional parameters for the LLM

        Returns:
            Generated text or None on error
        """
        try:
            self.logger.debug(f"Generating text for prompt: '{prompt[:50]}...'")
            response = self.llm.chat(prompt, **kwargs)
            return response
        except Exception as e:
            self.logger.error(f"Text generation failed: {e}")
            return None

    def generate_image(self, prompt: str, generator: str = "dalle") -> Optional[str]:
        """Generate image using specified generator.

        Args:
            prompt: Image generation prompt
            generator: Generator to use ('dalle', 'sdxl')

        Returns:
            Path to generated image or None on error
        """
        try:
            self.logger.debug(f"Generating image with {generator}: '{prompt[:50]}...'")

            if generator == "dalle" and self.dalle:
                return self.dalle.generate(prompt)
            elif generator == "sdxl" and self.sdxl:
                return self.sdxl.generate(prompt)
            else:
                self.logger.warning(f"Image generator '{generator}' not available")
                return None

        except Exception as e:
            self.logger.error(f"Image generation failed: {e}")
            return None
