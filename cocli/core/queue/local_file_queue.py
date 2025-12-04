import json
import logging
import shutil
import time
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

from ...models.queue import QueueMessage
from . import QueueManager
from ...core.config import get_cocli_base_dir

logger = logging.getLogger(__name__)

class LocalFileQueue(QueueManager):
    """
    A file-system based queue implementation for local development.
    Uses directories for state management: pending, processing, failed.
    """

    def __init__(self, queue_name: str, visibility_timeout_seconds: int = 300):
        self.queue_name = queue_name
        self.visibility_timeout = visibility_timeout_seconds
        
        self.base_dir = get_cocli_base_dir() / "queues" / queue_name
        self.pending_dir = self.base_dir / "pending"
        self.processing_dir = self.base_dir / "processing"
        self.failed_dir = self.base_dir / "failed"
        self.completed_dir = self.base_dir / "completed"

        # Ensure directories exist
        for d in [self.pending_dir, self.processing_dir, self.failed_dir, self.completed_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def push(self, message: QueueMessage) -> str:
        """Writes the message to a JSON file in the pending directory."""
        file_path = self.pending_dir / f"{message.id}.json"
        with open(file_path, "w") as f:
            f.write(message.model_dump_json())
        logger.debug(f"Pushed message {message.id} to local queue {self.queue_name}")
        return message.id

    def poll(self, batch_size: int = 1) -> List[QueueMessage]:
        """
        Retrieves messages.
        1. Checks for expired messages in 'processing' and moves them back to 'pending'.
        2. Moves up to 'batch_size' messages from 'pending' to 'processing'.
        """
        self._reclaim_expired_messages()

        messages = []
        # List pending files, sort by modification time (FIFO-ish)
        pending_files = sorted(self.pending_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)

        for file_path in pending_files[:batch_size]:
            try:
                # Move to processing (atomic-ish on same filesystem)
                processing_path = self.processing_dir / file_path.name
                shutil.move(str(file_path), str(processing_path))
                
                # Touch the file to update mtime (start the visibility timer)
                processing_path.touch()

                # Read and parse
                with open(processing_path, "r") as f:
                    data = json.load(f)
                    message = QueueMessage(**data)
                    messages.append(message)
            except Exception as e:
                logger.error(f"Error polling message from file {file_path}: {e}")
                # If we can't move or read it, maybe move to failed?
                # For now, leave it or log it.
        
        return messages

    def ack(self, message: QueueMessage) -> None:
        """
        Deletes the message file from the processing directory.
        Optionally archives it to 'completed'.
        """
        processing_path = self.processing_dir / f"{message.id}.json"
        if processing_path.exists():
            # For debugging history, we might want to move to completed instead of unlink
            # processing_path.unlink()
            completed_path = self.completed_dir / processing_path.name
            shutil.move(str(processing_path), str(completed_path))
            logger.debug(f"Acked message {message.id}")
        else:
            logger.warning(f"Attempted to ack message {message.id} but file not found in processing.")

    def nack(self, message: QueueMessage, is_http_500: bool = False) -> None:
        """
        Moves the message back to pending for retry.
        If attempts exceed a threshold, move to failed.
        """
        processing_path = self.processing_dir / f"{message.id}.json"
        if processing_path.exists():
            # Update attempts
            message.attempts += 1
            if is_http_500:
                message.http_500_attempts += 1
            message.updated_at = datetime.utcnow()
            
            # Write updated metadata back to file
            with open(processing_path, "w") as f:
                f.write(message.model_dump_json())

            if message.attempts > 5: # Max total retries
                logger.warning(f"Message {message.id} exceeded max total retries. Moving to failed.")
                shutil.move(str(processing_path), str(self.failed_dir / processing_path.name))
            elif message.http_500_attempts > 2: # Max 500 retries
                logger.warning(f"Message {message.id} exceeded max HTTP 500 retries. Moving to failed.")
                shutil.move(str(processing_path), str(self.failed_dir / processing_path.name))
            else:
                logger.info(f"Nacking message {message.id}. Moving back to pending.")
                shutil.move(str(processing_path), str(self.pending_dir / processing_path.name))
        else:
            logger.warning(f"Attempted to nack message {message.id} but file not found in processing.")

    def _reclaim_expired_messages(self) -> None:
        """
        Checks 'processing' directory for files older than visibility_timeout.
        Moves them back to 'pending'.
        """
        now = time.time()
        for file_path in self.processing_dir.glob("*.json"):
            try:
                mtime = file_path.stat().st_mtime
                if (now - mtime) > self.visibility_timeout:
                    logger.warning(f"Message {file_path.name} expired in processing (stale worker). Reclaiming to pending.")
                    shutil.move(str(file_path), str(self.pending_dir / file_path.name))
            except Exception as e:
                logger.error(f"Error reclaiming message {file_path}: {e}")
