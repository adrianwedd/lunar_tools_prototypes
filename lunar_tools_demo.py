import argparse
import importlib
import inspect
import logging
import os
import sys

# Add the prototypes directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "prototypes"))


# Set up logging for the CLI
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _discover_demos():
    demo_map = {}
    prototypes_dir = os.path.join(os.path.dirname(__file__), "prototypes")
    for filename in os.listdir(prototypes_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]  # Remove .py extension
            try:
                module = importlib.import_module(module_name)
                # Assuming the class name is the camel-cased version of the module name
                class_name = "".join(
                    [s.capitalize() for s in module_name.replace("-", "_").split("_")]
                )
                if hasattr(module, class_name):
                    demo_map[module_name.replace("_", "-")] = {
                        "module": module_name,
                        "class": class_name,
                    }
                else:
                    logger.warning(
                        f"Could not find class {class_name} in module {module_name}. Skipping."
                    )
            except Exception as e:
                logger.warning(f"Could not import module {module_name}: {e}. Skipping.")
    return demo_map


def main():
    parser = argparse.ArgumentParser(description="Launch Lunar Tools Art Demos.")
    parser.add_argument(
        "--demo",
        type=str,
        required=True,
        help="Name of the demo to launch (e.g., interactive-storytelling, apocalypse-experience).",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Optional configuration for the demo (e.g., 'recording_duration=5,summary_interval=10').",
    )

    args = parser.parse_args()

    demo_name = args.demo
    config_str = args.config

    demo_map = _discover_demos()

    if demo_name not in demo_map:
        logger.error(
            f"Unknown demo '{demo_name}'. Available demos: {', '.join(demo_map.keys())}"
        )
        sys.exit(1)

    demo_info = demo_map[demo_name]
    module_name = demo_info["module"]
    class_name = demo_info["class"]

    try:
        module = importlib.import_module(module_name)
        demo_class = getattr(module, class_name)

        config_kwargs = {}
        if config_str:
            for item in config_str.split(","):
                if "=" in item:
                    key, value = item.split("=", 1)
                    config_kwargs[key.strip()] = _parse_config_value(value.strip())

        from src.lunar_tools_art.manager import Manager

        lunar_tools_art_manager = Manager()

        # Inspect the constructor to determine if lunar_tools_art_manager is expected
        # This makes the instantiation more generic
        if (
            "lunar_tools_art_manager"
            in inspect.signature(demo_class.__init__).parameters
        ):
            demo_instance = demo_class(lunar_tools_art_manager, **config_kwargs)
        else:
            demo_instance = demo_class(**config_kwargs)

        demo_instance.run()

    except ImportError as e:
        logger.error(
            f"Could not import module '{module_name}'. Please ensure the file exists in the 'prototypes/' directory and there are no syntax errors. Details: {e}"
        )
        sys.exit(1)
    except AttributeError as e:
        logger.error(
            f"Could not find class '{class_name}' in module '{module_name}'. Please ensure the class name is correct and matches the file naming convention. Details: {e}"
        )
        sys.exit(1)
    except TypeError as e:
        logger.error(
            f"The demo class '{class_name}' could not be instantiated with the provided arguments. Please check the constructor signature and the --config parameters. Details: {e}"
        )
        sys.exit(1)
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while running the demo '{demo_name}': {e}"
        )
        sys.exit(1)


def _parse_config_value(value_str):
    """Safely parses a string value into its appropriate Python type."""
    if value_str.lower() == "true":
        return True
    if value_str.lower() == "false":
        return False
    if value_str.isdigit():
        return int(value_str)
    try:
        return float(value_str)
    except ValueError:
        pass
    if value_str.startswith("(") and value_str.endswith(")"):
        try:
            return tuple(map(_parse_config_value, value_str[1:-1].split(",")))
        except Exception:
            pass
    return value_str


if __name__ == "__main__":
    main()
