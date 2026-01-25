from typing import Any, Optional
from .local_file_queue import LocalFileQueue
from .sqs_queue import SQSQueue
from .scrape_sqs_queue import ScrapeSQSQueue
from .gm_item_sqs_queue import GmItemSQSQueue
from .command_sqs_queue import CommandSQSQueue

import logging

logger = logging.getLogger(__name__)

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
    # Priority: Env Var > Campaign Config > Global Config > Default (SQS if use_cloud, else LocalFile)
    provider = os.getenv("COCLI_QUEUE_TYPE")
    
    if not provider and effective_campaign:
        camp_config = load_campaign_config(effective_campaign)
        provider = camp_config.get("queue_type") or camp_config.get("campaign", {}).get("queue_type")

    if not provider:
        from ..config import get_config
        provider = get_config().queue_type
    
    if provider == "filesystem" and effective_campaign:
        from .filesystem import FilesystemGmListQueue, FilesystemGmDetailsQueue, FilesystemEnrichmentQueue
        from ..reporting import get_boto3_session
        
        s3_client = None
        bucket_name = None
        if use_cloud:
            config = load_campaign_config(effective_campaign)
            aws_config = config.get('aws', {})
            bucket_name = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name") or f"cocli-data-{effective_campaign}"
            
            try:
                session = get_boto3_session(config)
                s3_client = session.client("s3")
            except Exception:
                pass # Fallback to local only

        if queue_type in ["scrape", "gm-list"]:
            return FilesystemGmListQueue(campaign_name=effective_campaign, s3_client=s3_client, bucket_name=bucket_name)
        elif queue_type == "gm_list_item":
            return FilesystemGmDetailsQueue(campaign_name=effective_campaign, s3_client=s3_client, bucket_name=bucket_name)
        elif queue_type == "enrichment":
            return FilesystemEnrichmentQueue(campaign_name=effective_campaign, s3_client=s3_client, bucket_name=bucket_name)

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
                 logger.warning("COCLI_SCRAPE_TASKS_QUEUE_URL missing. Falling back to local.")
                 return LocalFileQueue(queue_name=queue_name)
            logger.debug(f"Using Scrape Queue URL: {queue_url}")
            return ScrapeSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        elif queue_type == "gm_list_item":
            queue_url = os.getenv("COCLI_GM_LIST_ITEM_QUEUE_URL") or aws_config.get("cocli_gm_list_item_queue_url")
            if not queue_url:
                 logger.warning("COCLI_GM_LIST_ITEM_QUEUE_URL missing. Falling back to local.")
                 return LocalFileQueue(queue_name=queue_name)
            logger.debug(f"Using GM List Item Queue URL: {queue_url}")
            return GmItemSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        elif queue_type == "command":
            queue_url = os.getenv("COCLI_COMMAND_QUEUE_URL") or aws_config.get("cocli_command_queue_url")
            if not queue_url:
                 logger.warning("COCLI_COMMAND_QUEUE_URL missing. Falling back to local.")
                 return LocalFileQueue(queue_name=queue_name)
            logger.debug(f"Factory creating CommandSQSQueue for {queue_url}")
            return CommandSQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
        else:
            queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL") or aws_config.get("cocli_enrichment_queue_url")
            if not queue_url:
                 logger.warning("COCLI_ENRICHMENT_QUEUE_URL missing. Falling back to local.")
                 return LocalFileQueue(queue_name=queue_name)
            logger.debug(f"Using Enrichment Queue URL: {queue_url}")
            return SQSQueue(queue_url=queue_url, aws_profile_name=aws_profile)
    else:
        return LocalFileQueue(queue_name=queue_name)
