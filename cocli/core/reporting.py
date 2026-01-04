import os
import boto3 
import logging
import yaml
from typing import Dict, Any, Literal, Sequence, cast
from rich.console import Console

from cocli.core.config import get_cocli_base_dir, get_companies_dir, load_campaign_config
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.email_index_manager import EmailIndexManager
from cocli.core.text_utils import slugify

logger = logging.getLogger(__name__)
console = Console()

__all__ = ['get_campaign_stats', 'get_boto3_session', 'load_campaign_config']

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
    """Creates a boto3 session using the campaign's AWS profile and region."""
    if os.getenv("COCLI_RUNNING_IN_FARGATE"):
        return boto3.Session()
    
    aws_config = campaign_config.get('aws', {})
    profile = aws_config.get('profile') or aws_config.get('aws_profile')
    region = aws_config.get('region')
    
    return boto3.Session(profile_name=profile, region_name=region)

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

    # 1. Local Prospects Count & Sources
    manager = ProspectsIndexManager(campaign_name)
    total_prospects = 0
    source_counts = {"local-worker": 0, "fargate-worker": 0, "unknown": 0}

    if manager.index_dir.exists():
        for prospect in manager.read_all_prospects():
            total_prospects += 1
            source = prospect.processed_by or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1
            
    stats['prospects_count'] = total_prospects
    stats['worker_stats'] = source_counts

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

    # 4. Email Index Yield
    email_manager = EmailIndexManager(campaign_name)
    indexed_emails = set()
    companies_in_email_index = set()
    for entry in email_manager.read_all_emails():
        indexed_emails.add(entry.email)
        if entry.company_slug:
            companies_in_email_index.add(entry.company_slug)
    
    stats['indexed_emails_count'] = len(indexed_emails)
    stats['indexed_companies_with_emails_count'] = len(companies_in_email_index)

    # 5. Enriched & Emails (Scan companies - Fallback/Legacy)
    enriched_count = 0
    emails_found_count = 0
    
    companies_dir = get_companies_dir()
    
    # Load target slugs from prospects index for fallback cross-referencing
    target_slugs = set()
    if manager.index_dir.exists():
        for prospect in manager.read_all_prospects():
            if prospect.Domain:
                target_slugs.add(slugify(prospect.Domain))

    # We scan all companies to find those tagged with this campaign or in the index
    for company_dir in companies_dir.iterdir():
        if not company_dir.is_dir():
            continue
            
        tags_path = company_dir / "tags.lst"
        has_tag = False
        if tags_path.exists():
            try:
                tags = tags_path.read_text().strip().splitlines()
                if campaign_name in tags:
                    has_tag = True
            except Exception:
                pass
        
        in_index = company_dir.name in target_slugs

        if not has_tag and not in_index:
            continue
            
        website_md = company_dir / "enrichments" / "website.md"
        index_md = company_dir / "_index.md"

        if website_md.exists():
            enriched_count += 1
            
        if not website_md.exists() and not index_md.exists():
            continue

        emails = set()

        # Check _index.md (Compiled data)
        if index_md.exists():
            try:
                content = index_md.read_text()
                if "email: " in content:
                    # Use a more robust check if possible, or just look for the line
                    for line in content.splitlines():
                        if line.startswith("email:"):
                            e = line.split(":", 1)[1].strip().strip("'").strip('"')
                            if e and e not in ["null", "''", ""]:
                                emails.add(e)
                                break
            except Exception:
                pass

        # Check website.md (Raw enrichment data)
        if website_md.exists():
            try:
                content = website_md.read_text()
                if content.startswith("---"):
                    parts = content.split("---")
                    if len(parts) >= 3:
                        data = yaml.safe_load(parts[1])
                        if data:
                            email = data.get("email")
                            personnel = data.get("personnel", [])
                            
                            if email and email not in ["null", "''", ""]: 
                                emails.add(email)
                            
                            if personnel:
                                for p in personnel:
                                    if isinstance(p, dict) and p.get("email"):
                                        emails.add(p["email"])
                                    elif isinstance(p, str) and "@" in p: 
                                         emails.add(p)
            except Exception:
                pass

        if emails:
            emails_found_count += 1

    stats['enriched_count'] = enriched_count
    stats['companies_with_emails_count'] = max(emails_found_count, stats.get('indexed_companies_with_emails_count', 0))
    stats['emails_found_count'] = stats.get('indexed_emails_count', 0)
    
    # 6. Configuration Data (Queries & Locations)    
    prospecting_config = config.get('prospecting', {})
    stats['queries'] = prospecting_config.get('queries', [])
    
    # Locations can be in the list or in a CSV
    locations = prospecting_config.get('locations', [])
    target_locations_csv = prospecting_config.get('target-locations-csv')
    
    if target_locations_csv:
        csv_path = get_cocli_base_dir() / "campaigns" / campaign_name / target_locations_csv
        if csv_path.exists():
            import csv
            try:
                with open(csv_path, 'r') as f:
                    reader = csv.DictReader(f)
                    # Just collect names/cities to keep JSON size reasonable
                    csv_locations = []
                    for row in reader:
                        name = row.get('name') or row.get('city')
                        if name:
                            csv_locations.append(name)
                    # Merge with explicit list if any
                    locations = list(set(locations + csv_locations))
            except Exception as e:
                logger.warning(f"Could not read target locations CSV: {e}")

    stats['locations'] = sorted(locations)

    return stats
