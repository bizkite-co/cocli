
import collections
import logging
import sys
import time
from datetime import datetime
from typing import Deque, Optional

from pathlib import Path


class RollingErrorCounter(logging.Handler):
    """Counts ERROR+ log records seen in a trailing time window, and keeps
    the last few formatted messages.

    Replaces `docker logs --since 30m | grep -icE 'error|exception|...'` with an
    in-process count (and now message sample) workers can report on their
    own heartbeat, instead of a remote log-grep the audit tool has to poll
    for - and unlike a remote grep, this isn't affected by log rotation (or
    the current lack of it - see docker-log-rotation-not-configured-on-pi-nodes).
    """

    def __init__(self, level: int = logging.ERROR, max_messages: int = 50) -> None:
        super().__init__(level=level)
        self._timestamps: Deque[float] = collections.deque()
        self._messages: Deque[str] = collections.deque(maxlen=max_messages)

    def emit(self, record: logging.LogRecord) -> None:
        self._timestamps.append(time.time())
        try:
            self._messages.append(self.format(record))
        except Exception:
            self._messages.append(record.getMessage())

    def count_since(self, seconds: float) -> int:
        cutoff = time.time() - seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        return len(self._timestamps)

    def recent_messages(self) -> list[str]:
        """Last max_messages ERROR+ records, oldest first. Not time-windowed
        like count_since - a fixed-count sample, so it stays cheap and
        bounded regardless of how bursty errors get."""
        return list(self._messages)


_error_counter: Optional[RollingErrorCounter] = None


def get_recent_error_count(window_s: float = 1800.0) -> int:
    """Number of ERROR+ log records emitted in the last `window_s` seconds."""
    if _error_counter is None:
        return 0
    return _error_counter.count_since(window_s)


def get_recent_error_messages() -> list[str]:
    """Last ~20 ERROR+ formatted messages this process has logged, oldest
    first. Empty if logging isn't set up yet (no worker process running)."""
    if _error_counter is None:
        return []
    return _error_counter.recent_messages()


def setup_file_logging(command_name: str, console_level: int = logging.INFO, file_level: int = logging.DEBUG, disable_console: bool = False) -> None:
    """
    Sets up logging to a file for a specific command and adjusts console output level.
    For the TUI, it uses a static filename.
    """
    log_dir = Path(".logs")
    log_dir.mkdir(exist_ok=True)

    if command_name == "tui":
        log_file = log_dir / "tui.log"
        # Overwrite the log file for TUI sessions for predictability
        # if log_file.exists():
        #     log_file.unlink()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{timestamp}_{command_name}.log"

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
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S %z')
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    global _error_counter
    _error_counter = RollingErrorCounter()
    root_logger.addHandler(_error_counter)

    if not disable_console:
        # Docker captures both stdout and stderr. By using stderr for all console logs,
        # we avoid buffering issues and ensure visibility in docker logs.
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S %z') # Keep console output clean
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Suppress noise from third-party libraries
    logging.getLogger("watchdog").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.INFO)
    logging.getLogger("botocore").setLevel(logging.INFO)
    logging.getLogger("s3transfer").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)

