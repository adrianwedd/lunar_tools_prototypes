"""
Shared utility functions for Lunar Tools Art prototypes.

This module provides common functionality used across multiple prototypes
to reduce code duplication and improve maintainability.
"""

import logging
import os
import tempfile
import time
import uuid
from typing import Callable, Optional

import numpy as np
from PIL import Image


def create_secure_temp_file(
    suffix: str = "", prefix: str = "lunar_tools_", directory: Optional[str] = None
) -> str:
    """
    Create a secure temporary file with a unique name.

    Args:
        suffix: File extension (e.g., '.wav', '.png')
        prefix: Prefix for the filename
        directory: Directory to create the file in (uses system temp if None)

    Returns:
        Path to the created temporary file
    """
    unique_id = uuid.uuid4().hex[:8]
    temp_fd, temp_path = tempfile.mkstemp(
        suffix=suffix, prefix=f"{prefix}{unique_id}_", dir=directory
    )
    os.close(temp_fd)  # Close the file descriptor, keep the path
    return temp_path


def safe_file_cleanup(file_path: str, logger: logging.Logger) -> bool:
    """
    Safely remove a file with proper error handling.

    Args:
        file_path: Path to the file to remove
        logger: Logger instance for error messages

    Returns:
        True if file was removed successfully, False otherwise
    """
    if not file_path or not os.path.exists(file_path):
        return True

    try:
        os.remove(file_path)
        return True
    except OSError as e:
        logger.warning(f"Failed to remove {file_path}: {e}")
        return False


def handle_keyboard_quit(
    keyboard_input, quit_keys: list = None, logger: logging.Logger = None
) -> bool:
    """
    Check for quit key presses and handle graceful shutdown.

    Args:
        keyboard_input: Keyboard input handler instance
        quit_keys: List of keys that trigger quit (default: ['q', 'escape'])
        logger: Optional logger for quit messages

    Returns:
        True if quit was requested, False otherwise
    """
    if quit_keys is None:
        quit_keys = ["q", "escape"]

    for key in quit_keys:
        if keyboard_input.is_key_pressed(key):
            if logger:
                logger.info(f"Quit requested via '{key}' key")
            return True
    return False


def create_blank_canvas(
    width: int, height: int, color: tuple = (0, 0, 0)
) -> Image.Image:
    """
    Create a blank PIL Image canvas.

    Args:
        width: Canvas width in pixels
        height: Canvas height in pixels
        color: RGB color tuple for background (default: black)

    Returns:
        PIL Image instance
    """
    return Image.new("RGB", (width, height), color=color)


def save_image_safely(
    image: Image.Image, file_path: str, logger: logging.Logger
) -> bool:
    """
    Safely save a PIL Image with error handling.

    Args:
        image: PIL Image to save
        file_path: Destination file path
        logger: Logger for error messages

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        image.save(file_path)
        return True
    except Exception as e:
        logger.error(f"Failed to save image to {file_path}: {e}")
        return False


def validate_audio_file(file_path: str, logger: logging.Logger) -> bool:
    """
    Validate that an audio file exists and is accessible.

    Args:
        file_path: Path to audio file
        logger: Logger for error messages

    Returns:
        True if file is valid, False otherwise
    """
    if not file_path:
        logger.error("Audio file path is empty")
        return False

    if not os.path.exists(file_path):
        logger.error(f"Audio file not found: {file_path}")
        return False

    if not os.path.isfile(file_path):
        logger.error(f"Audio path is not a file: {file_path}")
        return False

    # Check file size (should be > 0)
    try:
        size = os.path.getsize(file_path)
        if size == 0:
            logger.error(f"Audio file is empty: {file_path}")
            return False
    except OSError as e:
        logger.error(f"Cannot access audio file {file_path}: {e}")
        return False

    return True


def validate_image_array(image_array: np.ndarray, logger: logging.Logger) -> bool:
    """
    Validate that a numpy array represents a valid image.

    Args:
        image_array: Numpy array representing an image
        logger: Logger for error messages

    Returns:
        True if array is valid, False otherwise
    """
    if image_array is None:
        logger.error("Image array is None")
        return False

    if not isinstance(image_array, np.ndarray):
        logger.error(f"Expected numpy array, got {type(image_array)}")
        return False

    if image_array.size == 0:
        logger.error("Image array is empty")
        return False

    # Check dimensions (should be 2D or 3D)
    if len(image_array.shape) not in [2, 3]:
        logger.error(f"Invalid image dimensions: {image_array.shape}")
        return False

    # If 3D, should have 3 or 4 channels (RGB or RGBA)
    if len(image_array.shape) == 3 and image_array.shape[2] not in [3, 4]:
        logger.error(f"Invalid number of channels: {image_array.shape[2]}")
        return False

    return True


def setup_prototype_logging(name: str, level: str = "INFO") -> logging.Logger:
    """
    Set up standardized logging for a prototype.

    Args:
        name: Name of the prototype (usually __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Don't add handlers if they already exist
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def measure_execution_time(func: Callable) -> Callable:
    """
    Decorator to measure and log function execution time.

    Args:
        func: Function to measure

    Returns:
        Wrapped function that logs execution time
    """

    def wrapper(*args, **kwargs):
        # Try to get logger from first argument (usually self)
        logger = None
        if args and hasattr(args[0], "logger"):
            logger = args[0].logger

        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            if logger:
                logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            if logger:
                logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
            raise

    return wrapper


def retry_operation(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator to retry operations with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay on each retry

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Try to get logger from first argument (usually self)
            logger = None
            if args and hasattr(args[0], "logger"):
                logger = args[0].logger

            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:  # Don't log on final attempt
                        if logger:
                            logger.warning(
                                f"{func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {current_delay}s..."
                            )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        if logger:
                            logger.error(
                                f"{func.__name__} failed after {max_attempts} attempts"
                            )

            # If we get here, all attempts failed
            raise last_exception

        return wrapper

    return decorator


# Common constants
DEFAULT_TEMP_FILE_PREFIX = "lunar_tools_"
DEFAULT_QUIT_KEYS = ["q", "escape"]
DEFAULT_CANVAS_COLOR = (0, 0, 0)  # Black

# File extension mappings
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}
