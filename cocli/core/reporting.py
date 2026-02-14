import os
import json
import boto3
import logging
import math
from typing import Dict, Any, cast, Union
from rich.console import Console

from cocli.core.config import get_cocli_base_dir, load_campaign_config
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.exclusions import ExclusionManager


logger = logging.getLogger(__name__)
console = Console()

__all__ = ["get_campaign_stats", "get_boto3_session", "load_campaign_config", "get_exclusions_data", "get_queries_data", "get_locations_data"]


def get_boto3_session(config: Dict[str, Any], max_pool_connections: int = 10) -> boto3.Session:
    """Creates a boto3 session, prioritizing IoT profiles for automatic refresh."""
    from botocore.config import Config
    boto_config = Config(max_pool_connections=max_pool_connections)
    aws_config = config.get("aws", {})
    
    # 1. Try explicit iot_profiles from config
    iot_profiles = aws_config.get("iot_profiles", [])
    if isinstance(iot_profiles, str):
        iot_profiles = [iot_profiles]
    
    for p in iot_profiles:
        try:
            session = boto3.Session(profile_name=p)
            # Test if it works
            session.client("sts", config=boto_config).get_caller_identity()
            logger.info(f"Using AWS IoT profile: {p}")
            return session
        except Exception as e:
            logger.debug(f"get_boto3_session: IoT profile {p} failed: {e}")
            continue

    # 2. Fallback to IoT script directly (Legacy/One-off)
    try:
        from ..utils.aws_iot_auth import get_iot_sts_credentials
        iot_creds = get_iot_sts_credentials()
        if iot_creds:
            logger.info("Using AWS IoT STS credentials via script fallback")
            return boto3.Session(
                aws_access_key_id=iot_creds["access_key"],
                aws_secret_access_key=iot_creds["secret_key"],
                aws_session_token=iot_creds["token"]
            )
    except Exception as e:
        logger.debug(f"get_boto3_session: IoT script fallback failed: {e}")

    # 3. Fallback to Profile in config (ONLY if it exists)
    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
    
    if profile_name:
        try:
            session = boto3.Session(profile_name=profile_name)
            session.client("sts", config=boto_config).get_caller_identity()
            logger.info(f"Using AWS profile from config: {profile_name}")
            return session
        except Exception as e:
            logger.debug(f"get_boto3_session: profile from config {profile_name} failed: {e}")
            pass

    # Final fallback: Default session (uses env vars like AWS_PROFILE or IAM roles)
    logger.info("Using default AWS session")
    return boto3.Session()


def get_active_fargate_tasks(
    session: boto3.Session,
    cluster_name: str = "ScraperCluster",
    service_name: str = "EnrichmentService",
) -> int:
    """
    Returns the number of running tasks for the specified ECS service.
    """
    try:
        ecs = session.client("ecs")
        response = ecs.describe_services(cluster=cluster_name, services=[service_name])
        services = response.get("services", [])
        if services:
            return cast(int, services[0].get("runningCount", 0))
        return 0
    except Exception as e:
        logger.warning(f"Could not fetch ECS service status: {e}")
        return 0

def get_exclusions_data(campaign_name: str) -> Dict[str, Any]:
    """Returns only the exclusions list."""
    exclusion_manager = ExclusionManager(campaign_name)
    exclusions = exclusion_manager.list_exclusions()
    data = {"exclusions": [exc.model_dump() for exc in exclusions]}
    for exc in data["exclusions"]:
        if exc.get("created_at"):
            exc["created_at"] = exc["created_at"].isoformat()
    return data

def get_queries_data(campaign_name: str) -> Dict[str, Any]:
    """Returns only the search queries."""
    config = load_campaign_config(campaign_name)
    return {"queries": config.get("prospecting", {}).get("queries", [])}

def get_locations_data(campaign_name: str) -> Dict[str, Any]:
    """Returns only the locations and their status."""
    config = load_campaign_config(campaign_name)
    prospecting_config = config.get("prospecting", {})
    proximity = prospecting_config.get("proximity", 30)
    
    # We'll reuse the logic from get_campaign_stats but just for locations
    # (Extracting this to a helper function later would be cleaner)
    stats = get_campaign_stats(campaign_name)
    return {
        "proximity": proximity,
        "locations": stats.get("locations", [])
    }

def get_campaign_stats(campaign_name: str) -> Dict[str, Any]:
    """
    Collects statistics for a campaign, including local file counts and cloud resource status.
    """
    from cocli.core.text_utils import slugify
    from datetime import datetime, timedelta, UTC
    import csv

    stats: Dict[str, Any] = {}

    # Load Config
    config = load_campaign_config(campaign_name)
    prospecting_config = config.get("prospecting", {})
    queries = prospecting_config.get("queries", [])
    stats["queries"] = queries

    # Initialize Tile Stats
    all_target_tiles: set[str] = set()
    all_scraped_tiles: set[str] = set()
    scraped_tiles_by_phrase: Dict[str, set[str]] = {q: set() for q in queries}
    witness_root = get_cocli_base_dir() / "indexes" / "scraped-tiles"

    # 0. Exclusions
    stats.update(get_exclusions_data(campaign_name))
    exclusion_manager = ExclusionManager(campaign_name)

    # 1. Local Prospects Count & Sources
    manager = ProspectsIndexManager(campaign_name)
    total_prospects = 0
    source_counts = {"local-worker": 0, "fargate-worker": 0, "unknown": 0}
    all_slugs: set[str] = set()
    prospect_metadata: Dict[str, str] = {} # slug -> name

    # Pre-calculate tile-to-prospect mapping for efficient location stats
    tile_prospect_counts: Dict[str, int] = {}

    from ..models.company import Company
    if manager.index_dir.exists():
        for prospect in manager.read_all_prospects():
            # Add to slugs list
            if prospect.company_slug:
                # Filter out raw Place IDs that might have leaked into slugs in old/malformed files
                if prospect.company_slug.startswith("ChIJ") and len(prospect.company_slug) > 20:
                    # Attempt to re-slugify from name if it's clearly a Place ID
                    from .text_utils import slugify
                    slug = slugify(prospect.name)
                else:
                    slug = prospect.company_slug
                
                all_slugs.add(slug)
                
                # Fetch clean name from Company model if not already cached
                if slug not in prospect_metadata:
                    comp = Company.get(slug)
                    if comp:
                        prospect_metadata[slug] = comp.name
                    else:
                        prospect_metadata[slug] = prospect.name or slug
                
            # Skip excluded
            if exclusion_manager.is_excluded(domain=prospect.domain, slug=prospect.company_slug):
                continue
                
            total_prospects += 1
            source = prospect.processed_by or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

            # Map prospect to its grid tile
            if prospect.latitude and prospect.longitude:
                sw_lat = (float(prospect.latitude) // 0.1) * 0.1
                sw_lon = (float(prospect.longitude) // 0.1) * 0.1
                tile_id = f"{sw_lat:.1f}_{sw_lon:.1f}"
                tile_prospect_counts[tile_id] = tile_prospect_counts.get(tile_id, 0) + 1

    stats["prospects_count"] = total_prospects
    stats["worker_stats"] = source_counts
    
    # 2. Queue Stats (Cloud vs Local)
    aws_config = config.get("aws", {})
    command_queue_url = aws_config.get("cocli_command_queue_url")

    if aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name"):
        stats["using_cloud_queue"] = True
        session = get_boto3_session(config)

        # Command Queue (Still used for remote commands via SQS for now)
        if command_queue_url:
            try:
                sqs = session.client("sqs")
                cmd_attrs = sqs.get_queue_attributes(
                    QueueUrl=command_queue_url, 
                    AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
                ).get("Attributes", {})
                stats["command_tasks_pending"] = int(cmd_attrs.get("ApproximateNumberOfMessages", 0))
                stats["command_tasks_inflight"] = int(cmd_attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
            except Exception:
                pass

        # Active Workers
        stats["active_fargate_tasks"] = get_active_fargate_tasks(session)

        # Cluster Capacity (DuckDB Live Analytics)
        from .analytics import get_cluster_capacity_stats
        try:
            stats["cluster_capacity"] = get_cluster_capacity_stats(campaign_name)
        except Exception as e:
            logger.warning(f"Failed to fetch live capacity stats: {e}")
            stats["cluster_capacity"] = {}

        # S3 Counts
        data_bucket = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name")
        if data_bucket:
            s3 = session.client("s3")
            
            # --- S3 Queue Progress (V2 Filesystem) ---
            s3_queues = {}
            for q in ["gm-list", "gm-details", "enrichment"]:
                try:
                    paginator = s3.get_paginator("list_objects_v2")
                    pending_count = 0
                    inflight_count = 0
                    prefix_pending = f"campaigns/{campaign_name}/queues/{q}/pending/"
                    for page in paginator.paginate(Bucket=data_bucket, Prefix=prefix_pending):
                        for obj in page.get("Contents", []):
                            if obj["Key"].endswith("task.json"):
                                pending_count += 1
                            elif obj["Key"].endswith("lease.json"):
                                inflight_count += 1
                    
                    # Special Case for gm-list pending: Use Mission vs Witness if pending is 0
                    if q == "gm-list" and pending_count == 0:
                        # This is an approximation. Real count is (target - witness)
                        # We use the counts we might already have or just leave it for now
                        # but at least we explain why it might be 0.
                        pass

                    completed_count = 0
                    prefix_completed = f"campaigns/{campaign_name}/queues/{q}/completed/"
                    for page in paginator.paginate(Bucket=data_bucket, Prefix=prefix_completed):
                        completed_count += len(page.get("Contents", []))
                    
                    s3_queues[q] = {
                        "pending": pending_count,
                        "inflight": inflight_count,
                        "completed": completed_count
                    }
                except Exception as e:
                    logger.warning(f"Could not count S3 queue tasks for {q}: {e}")
            
            # --- Better gm-list (Global) Pending count ---
            # If we already scanned scraped tiles from S3, we can use that.
            if "gm-list" in s3_queues:
                # We can use total_target_tiles and total_scraped_tiles calculated below
                # But those are calculated AFTER this loop.
                pass
            # ---------------------------------------------
            
            stats["s3_queues"] = s3_queues
            # ----------------------------------------

            # --- Heartbeats ---
            try:
                heartbeats = []
                response = s3.list_objects_v2(Bucket=data_bucket, Prefix="status/")
                for obj in response.get("Contents", []):
                    if obj["Key"].endswith(".json"):
                        try:
                            hb_data = s3.get_object(Bucket=data_bucket, Key=obj["Key"])
                            hb_json = json.loads(hb_data["Body"].read().decode("utf-8"))
                            # Add last_seen from S3 metadata
                            hb_json["last_seen"] = obj["LastModified"].isoformat()
                            heartbeats.append(hb_json)
                        except Exception as hb_err:
                            logger.warning(f"Failed to read heartbeat {obj['Key']}: {hb_err}")
                stats["worker_heartbeats"] = heartbeats
            except Exception as e:
                logger.warning(f"Could not fetch worker heartbeats: {e}")
                stats["worker_heartbeats"] = []

            # --- Global Scraped Tiles from S3 ---
            try:
                paginator = s3.get_paginator("list_objects_v2")
                prefix = f"campaigns/{campaign_name}/indexes/scraped-tiles/"
                remote_scraped_by_phrase: Dict[str, set[str]] = {slugify(q): set() for q in queries}
                
                for page in paginator.paginate(Bucket=data_bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        if key.endswith(".csv") or key.endswith(".usv"):
                            parts = key.split("/")
                            if len(parts) >= 3:
                                phrase_slug = parts[-1].replace(".csv", "").replace(".usv", "")
                                lat_str = parts[-3]
                                lon_str = parts[-2]
                                tile_id = f"{lat_str}_{lon_str}"
                                if phrase_slug in remote_scraped_by_phrase:
                                    remote_scraped_by_phrase[phrase_slug].add(tile_id)
                
                for q in queries:
                    q_slug = slugify(q)
                    if q_slug in remote_scraped_by_phrase:
                        for tid in remote_scraped_by_phrase[q_slug]:
                            all_scraped_tiles.add(tid)
                            scraped_tiles_by_phrase[q].add(tid)

            except Exception as e:
                logger.warning(f"Could not fetch global scraped tiles from S3: {e}")
    else:
        stats["using_cloud_queue"] = False

    # Always check Local queue stats (for RPI cluster / Filesystem mode)
    from .paths import paths
    local_stats = {}
    for q_name in ["gm-list", "gm-details", "enrichment"]:
        queue_base = paths.queue(campaign_name, q_name)
        pending_dir = queue_base / "pending"
        completed_dir = queue_base / "completed"

        q_pending = 0
        q_inflight = 0
        q_completed = 0

        if pending_dir.exists():
            try:
                with os.scandir(pending_dir) as entries:
                    for entry in entries:
                        if entry.is_dir():
                            q_pending += 1
            except Exception:
                pass
            
            # Count leases for inflight
            q_inflight = len(list(pending_dir.glob("*/lease.json")))

        if completed_dir.exists():
             q_completed = len(list(completed_dir.glob("*.json")))
        
        local_stats[q_name] = {
            "pending": q_pending,
            "inflight": q_inflight,
            "completed": q_completed
        }

    stats["local_queues"] = local_stats
    
    # --- Mission Index Awareness for gm-list ---
    # If the virtual queue (target-tiles) has items, count them as pending
    # unless they are already in the witness index.
    campaign_dir = paths.campaign(campaign_name)
    target_tiles_dir = campaign_dir / "indexes" / "target-tiles"
    if target_tiles_dir.exists():
        mission_pending = 0
        for tf in list(target_tiles_dir.glob("**/*.csv")) + list(target_tiles_dir.glob("**/*.usv")):
            rel_path = tf.relative_to(target_tiles_dir)
            witness_csv = witness_root / rel_path.with_suffix(".csv")
            witness_usv = witness_root / rel_path.with_suffix(".usv")
            if not witness_csv.exists() and not witness_usv.exists():
                mission_pending += 1
        
        # Merge mission pending into the gm-list pending count
        if "gm-list" in local_stats:
            local_stats["gm-list"]["pending"] += mission_pending
        else:
            local_stats["gm-list"] = {"pending": mission_pending, "inflight": 0, "completed": 0}
    # --------------------------------------------

    # Legacy compatibility for enrichment stats
    stats["local_enrichment_pending"] = local_stats["enrichment"]["pending"]
    stats["local_enrichment_inflight"] = local_stats["enrichment"]["inflight"]
    stats["local_enrichment_completed"] = local_stats["enrichment"]["completed"]

    # For simplicity in the combined report table, prefer S3 (Global) stats if available
    s3_stats = stats.get("s3_queues", {}).get("enrichment", {})
    if stats.get("using_cloud_queue") and s3_stats:
        stats["enrichment_pending"] = s3_stats.get("pending", 0)
        stats["enrichment_inflight"] = s3_stats.get("inflight", 0)
        stats["completed_count"] = s3_stats.get("completed", 0)
        stats["remote_enrichment_completed"] = s3_stats.get("completed", 0)
    else:
        stats["enrichment_pending"] = local_stats["enrichment"]["pending"]
        stats["enrichment_inflight"] = local_stats["enrichment"]["inflight"]
        stats["completed_count"] = local_stats["enrichment"]["completed"]

    # Old path stats (for cleanup monitoring)
    from .config import get_campaigns_dir
    campaign_dir = get_campaigns_dir() / campaign_name
    
    # GM Details stats
    details_frontier = campaign_dir / "frontier" / "gm-details"
    if details_frontier.exists():
        stats["local_gm_list_item_pending"] = len(
            list(details_frontier.glob("*.json"))
        )

    # 3. Enriched Companies & Emails
    from cocli.core.email_index_manager import EmailIndexManager

    email_index = EmailIndexManager(campaign_name)
    emails_found_count = 0
    domains_with_emails: set[str] = set()

    # We use the email index for primary counts
    for email_entry in email_index.read_all_emails():
        emails_found_count += 1
        if email_entry.domain:
            domains_with_emails.add(email_entry.domain)

    companies_with_emails_count = len(domains_with_emails)

    from cocli.core.config import get_companies_dir

    enriched_count = 0
    deep_enriched_count = 0
    # Fallback/validation counts from companies directory
    # (We still scan to get the total enriched_count for the tag)
    companies_dir = get_companies_dir()
    tag = config.get("campaign", {}).get("tag") or campaign_name

    # Scan companies directory
    if companies_dir.exists():
        for company_path in companies_dir.iterdir():
            if not company_path.is_dir():
                continue

            # Check tags.lst first (Fast)
            tags_file = company_path / "tags.lst"
            has_tag = False
            if tags_file.exists():
                try:
                    tags = tags_file.read_text().splitlines()
                    if tag in [t.strip() for t in tags]:
                        has_tag = True
                except Exception:
                    pass

            if has_tag:
                enriched_count += 1
                # Check for Deep Enrichment artifacts
                enrich_dir = company_path / "enrichments"
                if (enrich_dir / "sitemap.xml").exists() or (enrich_dir / "navbar.html").exists():
                    deep_enriched_count += 1

    stats["enriched_count"] = enriched_count
    stats["deep_enriched_count"] = deep_enriched_count
    # In this architecture, a completed task results in an enriched company file.
    # So we can use enriched_count as the proxy for completed items locally.
    stats["completed_count"] = enriched_count

    stats["companies_with_emails_count"] = companies_with_emails_count
    stats["emails_found_count"] = emails_found_count

    # Global Enrichment Count (Total pool from Manifest)
    try:
        from .domain_index_manager import DomainIndexManager
        from ..models.campaign import Campaign as CampaignModel
        idx_manager = DomainIndexManager(CampaignModel.load(campaign_name))
        # This might be slow if it has to bootstrap, but once manifest exists it is fast
        manifest = idx_manager.get_latest_manifest()
        stats["total_enriched_global"] = len(manifest.shards)
    except Exception as e:
        logger.warning(f"Could not fetch global pool count from manifest: {e}")
        # Fallback to local count
        total_global = 0
        if companies_dir.exists():
            for company_path in companies_dir.iterdir():
                if (company_path / "enrichments" / "website.md").exists():
                    total_global += 1
        stats["total_enriched_global"] = total_global

    # 5. Anomaly Detection (Bot Detection Monitoring) using new Witness Index
    total_scraped_tiles_witness = 0
    empty_scraped_tiles_witness = 0

    phrase_slugs = [slugify(q) for q in queries]
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)

    # Nested Witness Index Check
    if witness_root.exists():
        for phrase_slug in phrase_slugs:
            witness_files = list(witness_root.glob(f"**/{phrase_slug}.csv")) + list(witness_root.glob(f"**/{phrase_slug}.usv"))
            for phrase_file in witness_files:
                try:
                    with open(phrase_file, "r", encoding="utf-8") as f:
                        from ..utils.usv_utils import USVDictReader
                        reader: Union[USVDictReader, csv.DictReader[Any]]
                        if phrase_file.suffix == ".usv":
                            reader = USVDictReader(f)
                        else:
                            reader = csv.DictReader(f)
                        
                        try:
                            row = next(reader)
                        except (StopIteration, Exception):
                            continue

                        scrape_date_str = row.get("scrape_date")
                        if not scrape_date_str:
                            continue
                        scrape_date = datetime.fromisoformat(scrape_date_str)
                        if scrape_date.tzinfo is None:
                            scrape_date = scrape_date.replace(tzinfo=UTC)

                        if scrape_date > seven_days_ago:
                            total_scraped_tiles_witness += 1
                            if int(row.get("items_found", 0)) == 0:
                                empty_scraped_tiles_witness += 1
                except Exception:
                    continue

    stats["anomaly_stats"] = {
        "total_scrapes": total_scraped_tiles_witness,
        "empty_scrapes": empty_scraped_tiles_witness,
        "shadow_ban_risk": "HIGH"
        if total_scraped_tiles_witness > 10
        and (empty_scraped_tiles_witness / total_scraped_tiles_witness) > 0.4
        else "LOW",
    }

    # 6. Configuration Data (Queries & Locations)
    proximity = prospecting_config.get("proximity", 30)
    stats["proximity"] = proximity

    detailed_locations = []
    explicit_locations = prospecting_config.get("locations", [])
    
    # Track which names we've seen to avoid duplicates between list and CSV
    seen_names: set[str] = set()

    # Load Grid Definition to find tiles associated with each location
    target_locations_csv = prospecting_config.get("target-locations-csv")
    if target_locations_csv:
        csv_path = (
            get_cocli_base_dir() / "campaigns" / campaign_name / target_locations_csv
        )
        if csv_path.exists():
            try:
                with open(csv_path, "r") as f:
                    grid_reader: csv.DictReader[Any] = csv.DictReader(f)
                    for row in grid_reader:
                        name = row.get("name") or row.get("city")
                        if not name:
                            continue

                        lat_val = row.get("lat")
                        lon_val = row.get("lon")

                        if not lat_val or not lon_val:
                            detailed_locations.append(
                                {
                                    "name": name,
                                    "lat": None,
                                    "lon": None,
                                    "proximity": proximity,
                                    "valid_geocode": False,
                                    "tile_id": None,
                                    "tiles_count": 0,
                                    "scraped_tiles_count": 0,
                                    "prospects_count": 0,
                                }
                            )
                            seen_names.add(name)
                            continue

                        lat, lon = float(lat_val), float(lon_val)

                        # Calculate tiles for this location (Proximity-based)
                        deg_range = (proximity / 69.0) + 0.1
                        lat_min, lat_max = lat - deg_range, lat + deg_range
                        lon_min, lon_max = lon - deg_range, lon + deg_range

                        loc_tiles: list[str] = []
                        scraped_count = 0
                        loc_prospects = 0

                        # Iterate through possible tiles in range
                        curr_lat = math.floor(lat_min * 10) / 10
                        while curr_lat <= lat_max:
                            curr_lon = math.floor(lon_min * 10) / 10
                            while curr_lon <= lon_max:
                                t_id = f"{curr_lat:.1f}_{curr_lon:.1f}"
                                t_center_lat = curr_lat + 0.05
                                t_center_lon = curr_lon + 0.05
                                dist_deg = math.sqrt((t_center_lat - lat) ** 2 + (t_center_lon - lon) ** 2)
                                
                                if (dist_deg * 69.0) <= proximity:
                                    loc_tiles.append(t_id)
                                    all_target_tiles.add(t_id)
                                    
                                    # Check if ANY query has scraped this tile
                                    is_scraped_any = False
                                    lat_dir, lon_dir = t_id.split("_")
                                    tile_witness_dir = witness_root / lat_dir / lon_dir

                                    for q in queries:
                                        q_slug = slugify(q)
                                        if (tile_witness_dir / f"{q_slug}.csv").exists() or (tile_witness_dir / f"{q_slug}.usv").exists():
                                            is_scraped_any = True
                                            all_scraped_tiles.add(t_id)
                                            scraped_tiles_by_phrase[q].add(t_id)
                                            
                                    if is_scraped_any:
                                        scraped_count += 1
                                    loc_prospects += tile_prospect_counts.get(t_id, 0)

                                curr_lon += 0.1
                            curr_lat += 0.1

                        detailed_locations.append(
                            {
                                "name": name,
                                "lat": lat,
                                "lon": lon,
                                "proximity": proximity,
                                "valid_geocode": True,
                                "tile_id": f"{(lat // 0.1) * 0.1:.1f}_{(lon // 0.1) * 0.1:.1f}",
                                "tiles_count": len(loc_tiles),
                                "scraped_tiles_count": scraped_count,
                                "prospects_count": loc_prospects,
                            }
                        )
                        seen_names.add(name)
            except Exception as e:
                logger.warning(f"Could not read target locations CSV: {e}")

    # Add explicit locations from config.toml
    for loc_name in explicit_locations:
        if loc_name not in seen_names:
            detailed_locations.append(
                {
                    "name": loc_name,
                    "lat": None,
                    "lon": None,
                    "proximity": proximity,
                    "valid_geocode": False,
                    "tile_id": None,
                    "tiles_count": 0,
                    "scraped_tiles_count": 0,
                    "prospects_count": 0,
                }
            )

    stats["locations"] = detailed_locations
    stats["total_target_tiles"] = len(all_target_tiles)
    stats["total_scraped_tiles"] = len(all_scraped_tiles)
    stats["scraped_per_phrase"] = {q: len(tiles) for q, tiles in scraped_tiles_by_phrase.items()}

    # Update summary keys for gm-list and gm-details if using cloud
    if stats.get("using_cloud_queue") and "s3_queues" in stats:
        s3_list = stats["s3_queues"].get("gm-list", {})
        s3_details = stats["s3_queues"].get("gm-details", {})
        
        # We keep the 'scrape_tasks' naming for dashboard compatibility
        stats["scrape_tasks_pending"] = s3_list.get("pending", 0)
        stats["scrape_tasks_inflight"] = s3_list.get("inflight", 0)
        
        stats["gm_list_item_pending"] = s3_details.get("pending", 0)
        stats["gm_list_item_inflight"] = s3_details.get("inflight", 0)

    # Update S3 Queue Pending count for gm-list if using cloud (re-calculate based on tiles)
    if stats.get("using_cloud_queue") and "gm-list" in stats.get("s3_queues", {}):
        # Pending = Target - Scraped - Inflight
        inflight = stats["s3_queues"]["gm-list"]["inflight"]
        pending = max(0, len(all_target_tiles) - len(all_scraped_tiles) - inflight)
        stats["s3_queues"]["gm-list"]["pending"] = pending

    return stats
