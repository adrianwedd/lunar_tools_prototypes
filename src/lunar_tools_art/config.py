import os
import toml
import logging
import re
from dotenv import load_dotenv

load_dotenv()

class MissingConfigError(Exception):
    """Custom exception for missing configuration values."""
    pass

class PIIFilter(logging.Filter):
    """A logging filter to redact sensitive information."""
    def filter(self, record):
        # Define patterns for sensitive information (e.g., API keys, personal names)
        # This is a simplified example; real-world PII detection can be complex.
        patterns = [
            r"[A-Za-z0-9]{32,}", # Example: long alphanumeric strings (potential API keys)
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b" # Email addresses
        ]
        message = record.getMessage()
        for pattern in patterns:
            message = re.sub(pattern, "[REDACTED]", message)
        record.msg = message
        return True

class Config:
    def __init__(self, settings_file="settings.toml"):
        self._config = {}
        self._load_settings_from_file(settings_file)
        self._load_settings_from_env()
        self._setup_logging()

    def _load_settings_from_file(self, settings_file):
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                self._config.update(toml.load(f))

    def _load_settings_from_env(self):
        for key, value in os.environ.items():
            # Simple heuristic to convert env vars to nested dicts
            if '__' in key:
                parts = key.lower().split('__')
                current_dict = self._config
                for part in parts[:-1]:
                    current_dict = current_dict.setdefault(part, {})
                current_dict[parts[-1]] = value
            else:
                self._config[key.lower()] = value

    def get(self, key, default=None):
        parts = key.lower().split('.')
        value = self._config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def get_or_raise(self, key):
        value = self.get(key)
        if value is None:
            raise MissingConfigError(f"Missing required configuration key: {key}")
        return value

    def _setup_logging(self):
        log_level_str = self.get("logging.level", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler() # Stream to stdout
            ]
        )
        # Add PII filter to all handlers
        for handler in logging.root.handlers:
            handler.addFilter(PIIFilter())
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Logging configured.")

config = Config()
