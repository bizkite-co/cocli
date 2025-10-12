
import logging
import os
from pathlib import Path
import sys
from datetime import datetime

from .config import get_cocli_base_dir

def setup_logging(level=logging.INFO):
    """
    Sets up basic application-wide logging to the console.
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout, # Default to stdout
    )
    logging.getLogger().setLevel(level)

def setup_file_logging(command_name: str, console_level=logging.INFO, file_level=logging.DEBUG, disable_console: bool = False):
    """
    Sets up logging to a timestamped file for a specific command and adjusts console output level.
    """
    log_dir = get_cocli_base_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{timestamp}_{command_name}.log"

    # Get the root logger
    root_logger = logging.getLogger()
    # Set logger to the most verbose level required by any handler
    effective_level = min(console_level, file_level) if not disable_console else file_level
    root_logger.setLevel(effective_level)

    # Clear existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create file handler for detailed logs
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(file_level)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    if not disable_console:
        # Create console handler for less verbose output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S') # Keep console output clean
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    logger = logging.getLogger(__name__)
    logger.info(f"Detailed logs for this run are being saved to: {log_file}")

