import logging
import os
from pathlib import Path

def setup_logging(log_file: str = "cocli.log", level=logging.INFO):
    """
    Sets up the application-wide logging configuration.
    """
    log_dir = Path("temp")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / log_file

    # Basic configuration for now, can be expanded later
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler() # Also log to console
        ]
    )
    # Set default level for the root logger
    logging.getLogger().setLevel(level)

    # Example of how to get a logger in other modules:
    # logger = logging.getLogger(__name__)
    # logger.info("This is an info message from a module.")
