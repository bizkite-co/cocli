from __future__ import annotations
from typing import Any, Literal, Optional, TYPE_CHECKING, overload
from .local_file_queue import LocalFileQueue
from .sqs_queue import SQSQueue
from .scrape_sqs_queue import ScrapeSQSQueue
from .gm_item_sqs_queue import GmItemSQSQueue
from .command_sqs_queue import CommandSQSQueue

if TYPE_CHECKING:
    from .protocol import CampaignQueueProtocol
    from .filesystem import FilesystemTileQueue

import logging

logger = logging.getLogger(__name__)


# FilesystemTileQueue is the one genuine oddball: no poll(), push() takes a
# Path (not a task), and workers move files pending→processing (dev/staging
# helpers) rather than CampaignQueueProtocol ack()/nack(). It does not (and
# should not) satisfy CampaignQueueProtocol, so it gets its own overload
# rather than joining the shared union below.
# mypy flags these two overloads as "overlapping" because queue_type: str in
# the second overload technically accepts the tile literals too — but overload
# resolution always tries this (keyword-only, more specific) one first, so
# real call sites resolve correctly; the overlap is a false positive here.
@overload
def get_queue_manager(  # type: ignore[overload-overlap]
    queue_name: str,
    use_cloud: bool = False,
    *,
    queue_type: Literal["tile", "map-tile", "tile-queue"],
    campaign_name: Optional[str] = None,
    s3_client: Optional[Any] = None,
) -> "FilesystemTileQueue": ...


@overload
def get_queue_manager(
    queue_name: str,
    use_cloud: bool = False,
    queue_type: str = "enrichment",
    campaign_name: Optional[str] = None,
    s3_client: Optional[Any] = None,
) -> "CampaignQueueProtocol[Any]": ...


def get_queue_manager(
    queue_name: str,
    use_cloud: bool = False,
    queue_type: str = "enrichment",
    campaign_name: Optional[str] = None,
    s3_client: Optional[Any] = None,
) -> Any:
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
    # Priority: Env Var > Campaign Config > Global Config > Default (Filesystem)
    provider = os.getenv("COCLI_QUEUE_TYPE")
    logger.info(f"Queue Factory: ENV COCLI_QUEUE_TYPE={provider}")
    
    if not provider and effective_campaign:
        camp_config = load_campaign_config(effective_campaign)
        provider = camp_config.get("queue_type") or camp_config.get("campaign", {}).get("queue_type")
        logger.info(f"Queue Factory: Config for {effective_campaign} queue_type={provider}")

    if not provider:
        from ..config import get_config
        provider = get_config().queue_type or "filesystem"
        logger.info(f"Queue Factory: Final fallback provider={provider}")
    
    logger.info(f"Queue Factory: Resolved provider={provider} for queue={queue_name} (campaign={effective_campaign})")
    
    if provider == "filesystem" and effective_campaign:
        from .filesystem import FilesystemGmListQueue, FilesystemGmDetailsQueue, FilesystemEnrichmentQueue, FilesystemTileQueue
        from ..reporting import get_boto3_session, get_data_bucket_name, get_s3_client

        active_s3_client = s3_client
        bucket_name = None
        if use_cloud:
            config = load_campaign_config(effective_campaign)
            bucket_name = get_data_bucket_name(config, effective_campaign)

            if not active_s3_client:
                try:
                    session = get_boto3_session(config)
                    active_s3_client = get_s3_client(session=session)
                except Exception:
                    pass # Fallback to local only

        if queue_type in ["scrape", "gm-list"]:
            return FilesystemGmListQueue(campaign_name=effective_campaign, s3_client=active_s3_client, bucket_name=bucket_name)
        elif queue_type in ["gm_list_item", "details"]:
            return FilesystemGmDetailsQueue(campaign_name=effective_campaign, s3_client=active_s3_client, bucket_name=bucket_name)
        elif queue_type == "enrichment":
            return FilesystemEnrichmentQueue(campaign_name=effective_campaign, s3_client=active_s3_client, bucket_name=bucket_name)
        elif queue_type in ["tile", "map-tile", "tile-queue"]:
            return FilesystemTileQueue(campaign_name=effective_campaign, s3_client=active_s3_client, bucket_name=bucket_name)

    if use_cloud:
        config = load_campaign_config(effective_campaign) if effective_campaign else {}
        aws_config = config.get('aws', {})
        
        # If running in Fargate, we MUST NOT use a profile name, 
        # as it should use the IAM Task Role.
        if os.getenv("COCLI_RUNNING_IN_FARGATE"):
            aws_profile = None
        else:
            from ..reporting import get_boto3_session
            # Prepare config for get_boto3_session
            config_obj = {"aws": aws_config, "campaign": {"name": effective_campaign}}
            session = get_boto3_session(config_obj)
            aws_profile = session.profile_name if session.profile_name != "default" else None
        
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
