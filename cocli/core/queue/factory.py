from typing import Any, Optional
from .local_file_queue import LocalFileQueue
from .sqs_queue import SQSQueue
from .scrape_sqs_queue import ScrapeSQSQueue
from .gm_item_sqs_queue import GmItemSQSQueue

def get_queue_manager(queue_name: str, use_cloud: bool = False, queue_type: str = "enrichment", campaign_name: Optional[str] = None) -> Any:
    """
    Factory to return the appropriate QueueManager.
    """
    if use_cloud:
        import os
        from ..config import get_campaign, load_campaign_config
        
        # Resolve campaign name if not provided
        effective_campaign = campaign_name
        if not effective_campaign:
            effective_campaign = get_campaign()
            
        config = load_campaign_config(effective_campaign) if effective_campaign else {}
        aws_config = config.get('aws', {})
        aws_profile = aws_config.get("profile") or aws_config.get("aws_profile")
        
        if queue_type == "scrape":
            queue_url = os.getenv("COCLI_SCRAPE_TASKS_QUEUE_URL") or aws_config.get("cocli_scrape_tasks_queue_url")
            if not queue_url:
                 raise ValueError("COCLI_SCRAPE_TASKS_QUEUE_URL (env) or 'cocli_scrape_tasks_queue_url' (config) must be set for cloud queue mode.")
            return ScrapeSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        elif queue_type == "gm_list_item":
            queue_url = os.getenv("COCLI_GM_LIST_ITEM_QUEUE_URL") or aws_config.get("cocli_gm_list_item_queue_url")
            if not queue_url:
                 raise ValueError("COCLI_GM_LIST_ITEM_QUEUE_URL (env) or 'cocli_gm_list_item_queue_url' (config) must be set for cloud queue mode.")
            return GmItemSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        else:
            queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL") or aws_config.get("cocli_enrichment_queue_url")
            if not queue_url:
                 raise ValueError("COCLI_ENRICHMENT_QUEUE_URL (env) or 'cocli_enrichment_queue_url' (config) must be set for cloud queue mode.")
            return SQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
    else:
        # TODO: Implement LocalFileQueue for ScrapeTasks if needed (different file structure?)
        # For now, LocalFileQueue is generic enough if we don't enforce strict typing inside it,
        # but LocalFileQueue expects QueueMessage.
        # We might need a LocalScrapeQueue later.
        return LocalFileQueue(queue_name=queue_name)
