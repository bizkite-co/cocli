import os
import boto3 
import logging
from typing import Dict, Any, Literal, Sequence, cast
from rich.console import Console

from cocli.core.config import get_cocli_base_dir, get_companies_dir, load_campaign_config
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.text_utils import slugify

logger = logging.getLogger(__name__)
console = Console()

SQSAttributeName = Literal[
    'AWSTraceHeader', 'All', 'ApproximateFirstReceiveTimestamp', 'ApproximateNumberOfMessages', 
    'ApproximateNumberOfMessagesDelayed', 'ApproximateNumberOfMessagesNotVisible', 
    'ApproximateReceiveCount', 'ContentBasedDeduplication', 'CreatedTimestamp', 
    'DeduplicationScope', 'DelaySeconds', 'FifoQueue', 'FifoThroughputLimit', 
    'KmsDataKeyReusePeriodSeconds', 'KmsMasterKeyId', 'LastModifiedTimestamp', 
    'MaximumMessageSize', 'MessageDeduplicationId', 'MessageGroupId', 
    'MessageRetentionPeriod', 'Policy', 'QueueArn', 'ReceiveMessageWaitTimeSeconds', 
    'RedriveAllowPolicy', 'RedrivePolicy', 'SenderId', 'SentTimestamp', 
    'SequenceNumber', 'SqsManagedSseEnabled', 'VisibilityTimeout'
]

def get_boto3_session(campaign_config: Dict[str, Any]) -> boto3.Session:
    """Creates a boto3 session using the campaign's AWS profile."""
    profile = campaign_config.get('aws', {}).get('profile') or campaign_config.get('aws', {}).get('aws_profile')
    if profile:
        return boto3.Session(profile_name=profile)
    return boto3.Session()

def get_sqs_attributes(session: boto3.Session, queue_url: str, attribute_names: Sequence[SQSAttributeName]) -> Dict[str, str]:
    try:
        sqs = session.client("sqs")
        response = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=list(attribute_names)
        )
        return cast(Dict[str, str], response.get('Attributes', {}))
    except Exception as e:
        logger.warning(f"Could not fetch SQS attributes for {queue_url}: {e}")
        return {}

def get_active_fargate_tasks(session: boto3.Session, cluster_name: str = "ScraperCluster", service_name: str = "EnrichmentService") -> int:
    """
    Returns the number of running tasks for the specified ECS service.
    """
    try:
        ecs = session.client("ecs")
        response = ecs.describe_services(cluster=cluster_name, services=[service_name])
        services = response.get('services', [])
        if services:
            return cast(int, services[0].get('runningCount', 0))
        return 0
    except Exception as e:
        logger.warning(f"Could not fetch ECS service status: {e}")
        return 0

def get_campaign_stats(campaign_name: str) -> Dict[str, Any]:
    """
    Collects statistics for a campaign, including local file counts and cloud resource status.
    """
    stats: Dict[str, Any] = {}
    
    # Load Config
    config = load_campaign_config(campaign_name)
    aws_config = config.get('aws', {})

    # 1. Local Prospects Count
    manager = ProspectsIndexManager(campaign_name)
    total_prospects = 0
    if manager.index_dir.exists():
        # Count root and inbox
        total_prospects = sum(1 for _ in manager.index_dir.glob("*.csv"))
        if manager.inbox_dir.exists():
            total_prospects += sum(1 for _ in manager.inbox_dir.glob("*.csv"))
    stats['prospects_count'] = total_prospects

    # 2. Queue Stats (Cloud vs Local)
    # Priority: Config > Env Var
    enrichment_queue_url = aws_config.get("cocli_enrichment_queue_url") or os.getenv("COCLI_ENRICHMENT_QUEUE_URL")
    scrape_tasks_queue_url = aws_config.get("cocli_scrape_tasks_queue_url") or os.getenv("COCLI_SCRAPE_TASKS_QUEUE_URL")
    gm_list_item_queue_url = aws_config.get("cocli_gm_list_item_queue_url") or os.getenv("COCLI_GM_LIST_ITEM_QUEUE_URL")
    
    using_cloud_queue = enrichment_queue_url is not None
    stats['using_cloud_queue'] = using_cloud_queue

    if using_cloud_queue and enrichment_queue_url:
        session = get_boto3_session(config)
        
        # Enrichment Queue
        attrs = get_sqs_attributes(session, enrichment_queue_url, ['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible'])
        stats['enrichment_pending'] = int(attrs.get('ApproximateNumberOfMessages', '0'))
        stats['enrichment_inflight'] = int(attrs.get('ApproximateNumberOfMessagesNotVisible', '0')) # Processing Now

        # Other Queues (Pending & In-Flight)
        if scrape_tasks_queue_url:
            attrs = get_sqs_attributes(session, scrape_tasks_queue_url, ['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible'])
            stats['scrape_tasks_pending'] = int(attrs.get('ApproximateNumberOfMessages', '0'))
            stats['scrape_tasks_inflight'] = int(attrs.get('ApproximateNumberOfMessagesNotVisible', '0'))
        
        if gm_list_item_queue_url:
            attrs = get_sqs_attributes(session, gm_list_item_queue_url, ['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible'])
            stats['gm_list_item_pending'] = int(attrs.get('ApproximateNumberOfMessages', '0'))
            stats['gm_list_item_inflight'] = int(attrs.get('ApproximateNumberOfMessagesNotVisible', '0'))
            
        # Active Workers (Fargate)
        stats['active_fargate_tasks'] = get_active_fargate_tasks(session)

    else:
        # Local Queues
        queue_base = get_cocli_base_dir() / "queues" / f"{campaign_name}_enrichment"
        stats['enrichment_pending'] = sum(1 for _ in (queue_base / "pending").iterdir() if _.is_file()) if (queue_base / "pending").exists() else 0
        stats['enrichment_inflight'] = sum(1 for _ in (queue_base / "processing").iterdir() if _.is_file()) if (queue_base / "processing").exists() else 0
        # No scrape/gm queues locally usually? Or structured similarly.
        stats['scrape_tasks_pending'] = 0 # Placeholder
        stats['gm_list_item_pending'] = 0 # Placeholder

    # 3. Local Failed/Completed
    queue_base = get_cocli_base_dir() / "queues" / f"{campaign_name}_enrichment"
    stats['failed_count'] = sum(1 for _ in (queue_base / "failed").iterdir() if _.is_file()) if (queue_base / "failed").exists() else 0
    stats['completed_count'] = sum(1 for _ in (queue_base / "completed").iterdir() if _.is_file()) if (queue_base / "completed").exists() else 0

    # 4. Enriched & Emails (Scan companies)
    enriched_count = 0
    emails_found_count = 0
    
    companies_dir = get_companies_dir()
    
    # We scan all companies to find those tagged with this campaign
    # This is more robust than just checking the prospect index
    for company_dir in companies_dir.iterdir():
        if not company_dir.is_dir():
            continue
            
        tags_path = company_dir / "tags.lst"
        if not tags_path.exists():
            continue
            
        try:
            tags = tags_path.read_text().strip().splitlines()
            if campaign_name not in tags:
                continue
        except Exception:
            continue
            
        # If we are here, the company is tagged for this campaign
        if (company_dir / "enrichments" / "website.md").exists():
            enriched_count += 1
            
            # Check for email
            index_path = company_dir / "_index.md"
            if index_path.exists():
                try:
                    content = index_path.read_text()
                    if "email: " in content and "email: null" not in content and "email: ''" not in content:
                        emails_found_count += 1
                except Exception:
                    pass

    stats['enriched_count'] = enriched_count
    stats['emails_found_count'] = emails_found_count
    
    return stats
