from typing import Any, Optional
from .local_file_queue import LocalFileQueue
from .sqs_queue import SQSQueue
from .scrape_sqs_queue import ScrapeSQSQueue
from .gm_item_sqs_queue import GmItemSQSQueue
from .command_sqs_queue import CommandSQSQueue

def get_queue_manager(queue_name: str, use_cloud: bool = False, queue_type: str = "enrichment", campaign_name: Optional[str] = None) -> Any:
    """
    Factory to return the appropriate QueueManager.
    """
    import os
    from ..config import get_campaign, load_campaign_config
    
    # Resolve campaign name if not provided
    effective_campaign = campaign_name
    if not effective_campaign:
        effective_campaign = get_campaign()

    # Determine Queue Provider (SQS or Filesystem)
    # Priority: Env Var > Config > Default (SQS if use_cloud, else LocalFile)
    provider = os.getenv("COCLI_QUEUE_TYPE")
    if not provider:
        from ..config import get_config
        provider = get_config().queue_type
    
    if provider == "filesystem" and effective_campaign:
        from .filesystem import FilesystemGmListQueue, FilesystemGmDetailsQueue, FilesystemEnrichmentQueue
        if queue_type in ["scrape", "gm-list"]:
            return FilesystemGmListQueue(campaign_name=effective_campaign)
        elif queue_type == "gm_list_item":
            return FilesystemGmDetailsQueue(campaign_name=effective_campaign)
        elif queue_type == "enrichment":
            return FilesystemEnrichmentQueue(campaign_name=effective_campaign)

    if use_cloud:
        config = load_campaign_config(effective_campaign) if effective_campaign else {}
        aws_config = config.get('aws', {})
        
        # If running in Fargate, we MUST NOT use a profile name, 
        # as it should use the IAM Task Role.
        if os.getenv("COCLI_RUNNING_IN_FARGATE"):
            aws_profile = None
        else:
            aws_profile = aws_config.get("profile") or aws_config.get("aws_profile")
        
        if queue_type == "scrape":
            queue_url = os.getenv("COCLI_SCRAPE_TASKS_QUEUE_URL") or aws_config.get("cocli_scrape_tasks_queue_url")
            if not queue_url:
                 raise ValueError("COCLI_SCRAPE_TASKS_QUEUE_URL (env) or 'cocli_scrape_tasks_queue_url' (config) must be set for cloud queue mode.")
            print(f"DEBUG: Using Scrape Queue URL: {queue_url}")
            return ScrapeSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        elif queue_type == "gm_list_item":
            queue_url = os.getenv("COCLI_GM_LIST_ITEM_QUEUE_URL") or aws_config.get("cocli_gm_list_item_queue_url")
            if not queue_url:
                 raise ValueError("COCLI_GM_LIST_ITEM_QUEUE_URL (env) or 'cocli_gm_list_item_queue_url' (config) must be set for cloud queue mode.")
            print(f"DEBUG: Using GM List Item Queue URL: {queue_url}")
            return GmItemSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        elif queue_type == "command":
            queue_url = os.getenv("COCLI_COMMAND_QUEUE_URL") or aws_config.get("cocli_command_queue_url")
            if not queue_url:
                 raise ValueError("COCLI_COMMAND_QUEUE_URL (env) or 'cocli_command_queue_url' (config) must be set for cloud queue mode.")
            print(f"DEBUG: Factory creating CommandSQSQueue for {queue_url}", flush=True)
            return CommandSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        else:
            queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL") or aws_config.get("cocli_enrichment_queue_url")
            if not queue_url:
                 raise ValueError("COCLI_ENRICHMENT_QUEUE_URL (env) or 'cocli_enrichment_queue_url' (config) must be set for cloud queue mode.")
            print(f"DEBUG: Using Enrichment Queue URL: {queue_url}")
            return SQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
    else:
        return LocalFileQueue(queue_name=queue_name)
