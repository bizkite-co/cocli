import os
import boto3 
import logging
import math
from typing import Dict, Any, Literal, Sequence, cast
from rich.console import Console

from cocli.core.config import get_cocli_base_dir, load_campaign_config
from cocli.core.prospects_csv_manager import ProspectsIndexManager

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

    # 1. Local Prospects Count & Sources
    manager = ProspectsIndexManager(campaign_name)
    total_prospects = 0
    source_counts = {"local-worker": 0, "fargate-worker": 0, "unknown": 0}
    
    # Pre-calculate tile-to-prospect mapping for efficient location stats
    tile_prospect_counts: Dict[str, int] = {}

    if manager.index_dir.exists():
        for prospect in manager.read_all_prospects():
            total_prospects += 1
            source = prospect.processed_by or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1
            
            # Map prospect to its grid tile
            if prospect.Latitude and prospect.Longitude:
                sw_lat = (float(prospect.Latitude) // 0.1) * 0.1
                sw_lon = (float(prospect.Longitude) // 0.1) * 0.1
                tile_id = f"{sw_lat:.1f}_{sw_lon:.1f}"
                tile_prospect_counts[tile_id] = tile_prospect_counts.get(tile_id, 0) + 1
            
    stats['prospects_count'] = total_prospects
    stats['worker_stats'] = source_counts

    # 2. Queue Stats (Cloud vs Local)
    aws_config = config.get('aws', {})
    enrich_queue_url = aws_config.get('cocli_enrichment_queue_url')
    scrape_queue_url = aws_config.get('cocli_scrape_tasks_queue_url')
    gm_queue_url = aws_config.get('cocli_gm_list_item_queue_url')

    if enrich_queue_url:
        stats['using_cloud_queue'] = True
        session = get_boto3_session(config)
        
        # Enrichment Queue
        enrich_attrs = get_sqs_attributes(session, enrich_queue_url, ['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible'])
        stats['enrichment_pending'] = int(enrich_attrs.get('ApproximateNumberOfMessages', 0))
        stats['enrichment_inflight'] = int(enrich_attrs.get('ApproximateNumberOfMessagesNotVisible', 0))

        # Scrape Tasks Queue
        if scrape_queue_url:
            scrape_attrs = get_sqs_attributes(session, scrape_queue_url, ['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible'])
            stats['scrape_tasks_pending'] = int(scrape_attrs.get('ApproximateNumberOfMessages', 0))
            stats['scrape_tasks_inflight'] = int(scrape_attrs.get('ApproximateNumberOfMessagesNotVisible', 0))

        # GM List Items Queue
        if gm_queue_url:
            gm_attrs = get_sqs_attributes(session, gm_queue_url, ['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible'])
            stats['gm_list_item_pending'] = int(gm_attrs.get('ApproximateNumberOfMessages', 0))
            stats['gm_list_item_inflight'] = int(gm_attrs.get('ApproximateNumberOfMessagesNotVisible', 0))

        # Active Workers
        stats['active_fargate_tasks'] = get_active_fargate_tasks(session)
    else:
        stats['using_cloud_queue'] = False
        # Local queue stats could be added here if implemented

    # 3. Enriched Companies & Emails
    # We use the email index for efficiency if it exists, otherwise scan
    from cocli.core.config import get_companies_dir
    import yaml

    enriched_count = 0
    companies_with_emails_count = 0
    emails_found_count = 0

    companies_dir = get_companies_dir()
    tag = config.get('campaign', {}).get('tag') or campaign_name

    # Scan companies directory
    if companies_dir.exists():
        for company_dir in companies_dir.iterdir():
            if not company_dir.is_dir():
                continue
            
            # Check tags.lst first (Fast)
            tags_file = company_dir / "tags.lst"
            has_tag = False
            if tags_file.exists():
                try:
                    tags = tags_file.read_text().splitlines()
                    if tag in [t.strip() for t in tags]:
                        has_tag = True
                except Exception:
                    pass
            
            if has_tag:
                # Read _index.md for email info
                index_file = company_dir / "_index.md"
                if index_file.exists():
                    try:
                        content = index_file.read_text()
                        if "---" in content:
                            parts = content.split("---")
                            if len(parts) >= 3:
                                fm = yaml.safe_load(parts[1])
                                if fm:
                                    enriched_count += 1
                                    if fm.get('email'):
                                        companies_with_emails_count += 1
                                    all_emails = fm.get('all_emails', [])
                                    if isinstance(all_emails, list):
                                        emails_found_count += len(all_emails)
                                    elif fm.get('email'):
                                        emails_found_count += 1
                    except Exception:
                        continue

    stats['enriched_count'] = enriched_count
    stats['companies_with_emails_count'] = companies_with_emails_count
    stats['emails_found_count'] = emails_found_count

    # 4. Scrape Index Status
    from cocli.core.scrape_index import ScrapeIndex
    scrape_index = ScrapeIndex()

    # 6. Configuration Data (Queries & Locations)    
    prospecting_config = config.get('prospecting', {})
    queries = prospecting_config.get('queries', [])
    stats['queries'] = queries
    proximity = prospecting_config.get('proximity', 30)
    stats['proximity'] = proximity
    
    detailed_locations = []
    explicit_locations = prospecting_config.get('locations', [])
    
    # Track which names we've seen to avoid duplicates between list and CSV
    seen_names = set()

    # Load Grid Definition to find tiles associated with each location
    # Tiles are associated with locations if they are within proximity.
    # We'll use a simplified version: any tile whose center is within proximity.
    target_locations_csv = prospecting_config.get('target-locations-csv')
    if target_locations_csv:
        csv_path = get_cocli_base_dir() / "campaigns" / campaign_name / target_locations_csv
        if csv_path.exists():
            import csv
            try:
                with open(csv_path, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get('name') or row.get('city')
                        if not name:
                            continue
                        
                        lat_val = row.get('lat')
                        lon_val = row.get('lon')
                        
                        if not lat_val or not lon_val:
                             detailed_locations.append({
                                "name": name, "lat": None, "lon": None, "proximity": proximity,
                                "valid_geocode": False, "tile_id": None, "tiles_count": 0, "scraped_tiles_count": 0, "prospects_count": 0
                            })
                             seen_names.add(name)
                             continue

                        lat, lon = float(lat_val), float(lon_val)
                        
                        # Calculate tiles for this location (Proximity-based)
                        # step_deg 0.1 is ~6.9 miles. 
                        # Proximity 30 miles -> roughly 4-5 tiles in each direction.
                        deg_range = (proximity / 69.0) + 0.1
                        lat_min, lat_max = lat - deg_range, lat + deg_range
                        lon_min, lon_max = lon - deg_range, lon + deg_range
                        
                        loc_tiles = []
                        scraped_count = 0
                        loc_prospects = 0
                        
                        # Iterate through possible tiles in range
                        curr_lat = math.floor(lat_min * 10) / 10
                        while curr_lat <= lat_max:
                            curr_lon = math.floor(lon_min * 10) / 10
                            while curr_lon <= lon_max:
                                t_id = f"{curr_lat:.1f}_{curr_lon:.1f}"
                                
                                # Distance check from tile center to location
                                t_center_lat = curr_lat + 0.05
                                t_center_lon = curr_lon + 0.05
                                
                                # Simple Euclidean distance in degrees for speed (approximate)
                                # 0.1 deg ~ 6.9 miles
                                dist_deg = math.sqrt((t_center_lat - lat)**2 + (t_center_lon - lon)**2)
                                if (dist_deg * 69.0) <= proximity:
                                    loc_tiles.append(t_id)
                                    # Check if ANY query has scraped this tile
                                    is_scraped = False
                                    for q in queries:
                                        if scrape_index.is_tile_scraped(q, t_id):
                                            is_scraped = True
                                            break
                                    if is_scraped:
                                        scraped_count += 1
                                    loc_prospects += tile_prospect_counts.get(t_id, 0)
                                    
                                curr_lon += 0.1
                            curr_lat += 0.1

                        detailed_locations.append({
                            "name": name,
                            "lat": lat,
                            "lon": lon,
                            "proximity": proximity,
                            "valid_geocode": True,
                            "tile_id": f"{(lat // 0.1) * 0.1:.1f}_{(lon // 0.1) * 0.1:.1f}",
                            "tiles_count": len(loc_tiles),
                            "scraped_tiles_count": scraped_count,
                            "prospects_count": loc_prospects
                        })
                        seen_names.add(name)
            except Exception as e:
                logger.warning(f"Could not read target locations CSV: {e}")

    # Add explicit locations from config.toml
    for loc_name in explicit_locations:
        if loc_name not in seen_names:
            detailed_locations.append({
                "name": loc_name,
                "lat": None,
                "lon": None,
                "proximity": proximity,
                "valid_geocode": False,
                "tile_id": None,
                "tiles_count": 0,
                "scraped_tiles_count": 0,
                "prospects_count": 0
            })

    stats['locations'] = detailed_locations

    return stats
