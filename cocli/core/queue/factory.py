from typing import Optional
from ..config import get_config
from . import QueueManager
from .local_file_queue import LocalFileQueue
from .sqs_queue import SQSQueue

def get_queue_manager(queue_name: str, use_cloud: bool = False) -> QueueManager:
    """
    Factory to return the appropriate QueueManager.
    """
    if use_cloud:
        # In a real scenario, we'd look up the SQS URL from config or convention
        # For now, we might need to pass it in or derive it.
        # Let's assume a config value or env var for now.
        import os
        queue_url = os.getenv("COCLI_SQS_QUEUE_URL")
        if not queue_url:
             raise ValueError("COCLI_SQS_QUEUE_URL environment variable must be set for cloud queue mode.")
        return SQSQueue(queue_url=queue_url)
    else:
        return LocalFileQueue(queue_name=queue_name)
