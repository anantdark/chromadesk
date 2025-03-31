# chromadesk/__main__.py
"""
Entry point for running ChromaDesk as a module using 'python -m chromadesk'.

This script simply imports and calls the main function from the main module.
"""

import logging
import sys

# Basic logging configuration as a fallback, though main.py should handle it primarily.
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger(__name__)

logger.debug("Executing ChromaDesk package via __main__.py")

try:
    # Use a relative import to get the main function from main.py
    # within the same package directory.
    from .main import main as main_entry_point
except ImportError as e:
    logger.critical(f"Failed to import main entry point from .main: {e}", exc_info=True)
    print(
        f"FATAL: Could not locate the main application logic within the package. Error: {e}",
        file=sys.stderr,
    )
    sys.exit(1)  # Exit with an error code

# Execute the main function and exit with its return code
if __name__ == "__main__":
    logger.debug("Calling main_entry_point...")
    exit_code = 1  # Default to error
    try:
        # Call the function that sets up args, logging, and runs GUI/headless
        exit_code = main_entry_point()
        logger.debug(f"main_entry_point returned: {exit_code}")
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred calling main_entry_point: {e}", exc_info=True
        )
        print(
            f"FATAL: An unexpected error occurred during execution: {e}",
            file=sys.stderr,
        )
        # Ensure exit_code remains non-zero or is set to 1
        exit_code = 1 if exit_code == 0 else exit_code

    sys.exit(exit_code)
