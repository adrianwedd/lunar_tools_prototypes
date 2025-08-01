"""
Exception handling utilities for Lunar Tools Art prototypes.

This module provides consistent exception handling patterns and utilities
for better error management across all prototypes.
"""

import functools
import logging
from typing import Any, Callable, Optional

import requests


class LunarToolsArtError(Exception):
    """Base exception for Lunar Tools Art prototypes."""

    pass


class ToolInitializationError(LunarToolsArtError):
    """Raised when a tool fails to initialize properly."""

    pass


class AIServiceError(LunarToolsArtError):
    """Raised when an AI service (GPT-4, DALL-E, etc.) fails."""

    pass


class NetworkError(LunarToolsArtError):
    """Raised when network operations fail."""

    pass


class ConfigurationError(LunarToolsArtError):
    """Raised when configuration is invalid or missing."""

    pass


def handle_ai_service_exceptions(
    logger: logging.Logger, service_name: str, fallback_value: Any = None
):
    """
    Decorator for handling common AI service exceptions with proper logging.

    Args:
        logger: Logger instance to use for error messages
        service_name: Name of the AI service for error messages
        fallback_value: Value to return on error (default: None)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"{service_name} connection failed: {e}")
                return fallback_value
            except requests.exceptions.Timeout as e:
                logger.warning(f"{service_name} request timed out: {e}")
                return fallback_value
            except requests.exceptions.HTTPError as e:
                logger.error(f"{service_name} HTTP error: {e}")
                return fallback_value
            except ValueError as e:
                logger.error(f"{service_name} invalid input/response: {e}")
                return fallback_value
            except KeyError as e:
                logger.error(f"{service_name} missing expected data: {e}")
                return fallback_value
            except Exception as e:
                logger.error(f"{service_name} unexpected error: {e}", exc_info=True)
                return fallback_value

        return wrapper

    return decorator


def handle_file_operations(
    logger: logging.Logger, operation_name: str, fallback_value: Any = None
):
    """
    Decorator for handling file operation exceptions.

    Args:
        logger: Logger instance to use for error messages
        operation_name: Description of the file operation
        fallback_value: Value to return on error (default: None)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except FileNotFoundError as e:
                logger.error(f"{operation_name} - file not found: {e}")
                return fallback_value
            except PermissionError as e:
                logger.error(f"{operation_name} - permission denied: {e}")
                return fallback_value
            except OSError as e:
                logger.error(f"{operation_name} - OS error: {e}")
                return fallback_value
            except Exception as e:
                logger.error(f"{operation_name} - unexpected error: {e}", exc_info=True)
                return fallback_value

        return wrapper

    return decorator


def handle_graceful_shutdown(
    logger: logging.Logger, cleanup_func: Optional[Callable] = None
):
    """
    Decorator for handling graceful shutdown on KeyboardInterrupt.

    Args:
        logger: Logger instance for shutdown messages
        cleanup_func: Optional cleanup function to call before shutdown
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal, cleaning up...")
                if cleanup_func:
                    try:
                        cleanup_func()
                    except Exception as e:
                        logger.error(f"Error during cleanup: {e}")
                logger.info("Shutdown complete")
                raise

        return wrapper

    return decorator


class ExceptionHandler:
    """
    Context manager for consistent exception handling in prototype main loops.
    """

    def __init__(
        self,
        logger: logging.Logger,
        prototype_name: str,
        continue_on_error: bool = True,
        max_consecutive_errors: int = 5,
    ):
        self.logger = logger
        self.prototype_name = prototype_name
        self.continue_on_error = continue_on_error
        self.max_consecutive_errors = max_consecutive_errors
        self.consecutive_errors = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            # No exception occurred, reset error counter
            self.consecutive_errors = 0
            return False

        if exc_type is KeyboardInterrupt:
            self.logger.info(f"{self.prototype_name} interrupted by user")
            return False  # Let KeyboardInterrupt propagate

        # Handle other exceptions
        self.consecutive_errors += 1
        self.logger.error(
            f"{self.prototype_name} error ({self.consecutive_errors}/{self.max_consecutive_errors}): {exc_value}",
            exc_info=True,
        )

        if self.consecutive_errors >= self.max_consecutive_errors:
            self.logger.critical(
                f"{self.prototype_name} reached maximum consecutive errors, shutting down"
            )
            return False  # Let exception propagate to shut down

        if self.continue_on_error:
            return True  # Suppress exception, continue execution
        else:
            return False  # Let exception propagate


# Common exception mapping for different types of operations
NETWORK_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
    ConnectionError,
    TimeoutError,
)

FILE_EXCEPTIONS = (
    FileNotFoundError,
    PermissionError,
    OSError,
    IOError,
)

VALIDATION_EXCEPTIONS = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)
