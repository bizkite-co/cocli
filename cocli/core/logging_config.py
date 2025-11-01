
import logging
import sys
from datetime import datetime

from .config import get_cocli_app_data_dir

def setup_file_logging(command_name: str, console_level: int = logging.INFO, file_level: int = logging.DEBUG, disable_console: bool = False) -> None:
    """
    Sets up logging to a file for a specific command and adjusts console output level.
    For the TUI, it uses a static filename.
    """
    log_dir = get_cocli_app_data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)

    if command_name == "tui":
        log_file = log_dir / "tui.log"
        # Overwrite the log file for TUI sessions for predictability
        # if log_file.exists():
        #     log_file.unlink()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{command_name}.log"

    # Get the root logger
    root_logger = logging.getLogger()
    # Set logger to the most verbose level required by any handler
    # If file_level is DEBUG, ensure root_logger is also DEBUG
    root_logger.setLevel(file_level)

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
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S') # Keep console output clean
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    logger = logging.getLogger(__name__)
    print(f"Detailed logs for this run are being saved to: {log_file}")

