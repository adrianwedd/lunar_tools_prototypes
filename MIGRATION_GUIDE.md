# Migration Guide: Using PrototypeBase Classes

This guide shows how to migrate existing prototypes to use the new standardized base classes for better consistency, error handling, and resource management.

## Base Classes Available

### `PrototypeBase`
- Core functionality for all prototypes
- Exception handling and resource management
- Configuration management
- Graceful shutdown patterns

### `InteractivePrototype`
- Extends PrototypeBase for user interaction
- Speech-to-text integration
- Audio recording management

### `AIPrototype`
- Extends PrototypeBase for AI-powered installations
- LLM integration helpers
- Image generation utilities

## Migration Steps

### Step 1: Update Imports

**Before:**
```python
class MyPrototype:
    def __init__(self, lunar_tools_art_manager):
        # ...
```

**After:**
```python
from src.lunar_tools_art.prototype_base import InteractivePrototype

class MyPrototype(InteractivePrototype):
    def __init__(self, lunar_tools_art_manager, **kwargs):
        super().__init__(lunar_tools_art_manager, **kwargs)
        # ...
```

### Step 2: Refactor Main Logic

**Before:**
```python
def run(self):
    self.logger.info("Starting...")
    while True:
        if self.keyboard_input.is_key_pressed("q"):
            break

        # Main logic here
        self.update_visuals()
        time.sleep(0.1)
```

**After:**
```python
def setup(self):
    """Initialize prototype - called once."""
    # Setup code here
    pass

def update(self):
    """Update state - called each loop iteration."""
    # Main logic here
    self.update_visuals()

def cleanup(self):
    """Clean up resources."""
    # Cleanup code here
    pass

# The base class handles the main loop, exit conditions, and error handling
```

### Step 3: Use Built-in Helper Methods

**Before:**
```python
# Manual configuration handling
self.max_particles = 50
if "max_particles" in config:
    self.max_particles = config["max_particles"]

# Manual error handling
try:
    result = self.llm.chat(prompt)
except Exception as e:
    self.logger.error(f"LLM error: {e}")
    result = None
```

**After:**
```python
# Standardized configuration with fallbacks
self.max_particles = self.get_config('max_particles', 50)

# Built-in error handling for AI services
result = self.generate_text(prompt)  # Returns None on error
```

## Example Migration: Whispers Prototype

### Original Structure
```python
class Whispers:
    def __init__(self, lunar_tools_art_manager):
        self.lunar_tools_art_manager = lunar_tools_art_manager
        self.renderer = self.lunar_tools_art_manager.renderer
        # ... more setup

    def run(self):
        while True:
            if self.keyboard_input.is_key_pressed("q"):
                break
            # Update logic
            time.sleep(0.05)
```

### Migrated Structure
```python
from src.lunar_tools_art.prototype_base import InteractivePrototype

class Whispers(InteractivePrototype):
    def __init__(self, lunar_tools_art_manager, **kwargs):
        super().__init__(lunar_tools_art_manager, loop_delay=0.05, **kwargs)

    def setup(self):
        # Initialize webcam, zones, particles
        self.webcam = self.manager.webcam
        self.particles = []
        self.zones = [...]

    def update(self):
        # Movement detection and particle updates
        self._detect_movement()
        self._update_particles()
        self._render_scene()

    def cleanup(self):
        # Clean up particles, close webcam
        self.particles.clear()
```

## Benefits of Migration

### 1. **Consistent Error Handling**
- Automatic exception catching and logging
- Graceful recovery from AI service failures
- Proper resource cleanup on errors

### 2. **Standardized Configuration**
- Unified config management with fallbacks
- Environment variable support
- Validation helpers

### 3. **Better Resource Management**
- Automatic cleanup on shutdown
- Context managers for resource tracking
- Memory leak prevention

### 4. **Enhanced Monitoring**
- Performance logging for slow operations
- Standardized log formats
- Better debugging information

### 5. **Simplified Development**
- Less boilerplate code
- Focus on art logic, not infrastructure
- Consistent patterns across prototypes

## Configuration Examples

### Basic Configuration
```python
config = {
    'loop_delay': 0.1,
    'max_particles': 100,
    'colors': ['red', 'blue', 'green']
}

prototype = MyPrototype(manager, **config)
```

### Environment-based Configuration
```python
# Uses settings.toml and environment variables
width = prototype.get_config('renderer.width', 800)
api_key = prototype.get_config('api_keys.openai')
```

### Required Configuration Validation
```python
def setup(self):
    # Validate required keys are present
    self.validate_config([
        'renderer.width',
        'renderer.height',
        'api_keys.openai'
    ])
```

## Testing Migrated Prototypes

### Unit Testing with Base Classes
```python
import pytest
from unittest.mock import Mock

def test_prototype_initialization():
    mock_manager = Mock()
    prototype = MyPrototype(mock_manager, test_param=42)

    assert prototype.get_config('test_param') == 42
    assert prototype.manager == mock_manager

def test_graceful_shutdown():
    prototype = MyPrototype(mock_manager)
    prototype.stop()

    assert prototype._running is False
```

### Smoke Testing
```python
def test_prototype_runs_without_error():
    manager = Manager()
    prototype = MyPrototype(manager)

    # Should not raise exceptions
    try:
        prototype.setup()
        prototype.update()  # Single iteration
        prototype.cleanup()
    finally:
        prototype.stop()
```

## Common Migration Patterns

### Pattern 1: Manual Loop → Base Class Loop
- Move initialization to `setup()`
- Move main logic to `update()`
- Move cleanup to `cleanup()`
- Remove manual exit checking

### Pattern 2: Direct Tool Access → Helper Methods
- Replace `self.manager.gpt4.chat()` with `self.generate_text()`
- Replace manual speech recording with `self.get_user_speech()`
- Use configuration helpers instead of direct access

### Pattern 3: Exception Handling → Automatic Handling
- Remove try/catch blocks for common operations
- Let base class handle logging and recovery
- Focus on art logic, not error management

## Migration Checklist

- [ ] Choose appropriate base class (PrototypeBase, InteractivePrototype, AIPrototype)
- [ ] Update class inheritance and imports
- [ ] Move initialization code to `setup()` method
- [ ] Move main loop logic to `update()` method
- [ ] Move cleanup code to `cleanup()` method
- [ ] Replace manual configuration with `get_config()`
- [ ] Use helper methods for common operations
- [ ] Test prototype works with new structure
- [ ] Update any existing tests
- [ ] Document prototype-specific configuration

Following this migration guide will result in more robust, maintainable, and consistent art installations while reducing boilerplate code.
