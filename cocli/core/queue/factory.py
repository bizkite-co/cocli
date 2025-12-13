from typing import Any
from .local_file_queue import LocalFileQueue
from .sqs_queue import SQSQueue
from .scrape_sqs_queue import ScrapeSQSQueue

def get_queue_manager(queue_name: str, use_cloud: bool = False, queue_type: str = "enrichment") -> Any:
    """
    Factory to return the appropriate QueueManager.
    """
    if use_cloud:
        # In a real scenario, we'd look up the SQS URL from config or convention
        # For now, we might need to pass it in or derive it.
        # Let's assume a config value or env var for now.
        import os
        
        if queue_type == "scrape":
            queue_url = os.getenv("COCLI_SCRAPE_TASKS_QUEUE_URL")
            if not queue_url:
                 raise ValueError("COCLI_SCRAPE_TASKS_QUEUE_URL environment variable must be set for cloud queue mode.")
            return ScrapeSQSQueue(queue_url=queue_url)
        else:
            queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL") or os.getenv("COCLI_ENRICHMENT_QUEUE_URL")
            if not queue_url:
                 raise ValueError("COCLI_ENRICHMENT_QUEUE_URL (or COCLI_ENRICHMENT_QUEUE_URL) environment variable must be set for cloud queue mode.")
            return SQSQueue(queue_url=queue_url)
    else:
        # TODO: Implement LocalFileQueue for ScrapeTasks if needed (different file structure?)
        # For now, LocalFileQueue is generic enough if we don't enforce strict typing inside it,
        # but LocalFileQueue expects QueueMessage.
        # We might need a LocalScrapeQueue later.
        return LocalFileQueue(queue_name=queue_name)
