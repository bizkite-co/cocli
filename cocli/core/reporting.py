import os
import json
import boto3
import logging
from typing import Dict, Any, cast, Optional
from rich.console import Console
from datetime import datetime, UTC

from cocli.core.config import get_cocli_base_dir, load_campaign_config
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.exclusions import ExclusionManager
from .paths import paths

logger = logging.getLogger(__name__)
console = Console()

__all__ = ["get_campaign_stats", "get_boto3_session", "load_campaign_config", "get_exclusions_data", "get_queries_data", "get_locations_data"]


def get_boto3_session(config: Dict[str, Any], max_pool_connections: int = 10, profile_name: Optional[str] = None) -> boto3.Session:
    """Creates a boto3 session, prioritizing explicit profile_name if provided."""
    aws_config = config.get("aws", {})
    campaign_name = config.get("campaign", {}).get("name")
    
    if profile_name:
        try:
            session = boto3.Session(profile_name=profile_name)
            logger.debug(f"Initialized forced AWS profile: {profile_name}")
            return session
        except Exception as e:
            logger.error(f"Failed to initialize forced profile {profile_name}: {e}")
            raise

    env_profile = os.environ.get("AWS_PROFILE")
    iot_profiles = aws_config.get("iot_profiles", [])
    if isinstance(iot_profiles, str):
        iot_profiles = [iot_profiles]
    
    if campaign_name:
        iot_profiles.insert(0, f"{campaign_name}-iot")
    
    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
    all_candidates = iot_profiles + ([profile_name] if profile_name else [])
    
    if env_profile and env_profile in all_candidates:
        try:
            session = boto3.Session(profile_name=env_profile)
            logger.debug(f"Initialized AWS profile from environment: {env_profile}")
            return session
        except Exception as e:
            logger.debug(f"get_boto3_session: Env profile {env_profile} initialization failed: {e}")

    for p in iot_profiles:
        if p == env_profile:
            continue
        try:
            session = boto3.Session(profile_name=p)
            logger.debug(f"Initialized AWS IoT profile: {p}")
            return session
        except Exception as e:
            logger.debug(f"get_boto3_session: IoT profile {p} initialization failed: {e}")
            continue

    try:
        from ..utils.aws_iot_auth import get_iot_sts_credentials
        iot_creds = get_iot_sts_credentials()
        if iot_creds:
            return boto3.Session(
                aws_access_key_id=iot_creds["access_key"],
                aws_secret_access_key=iot_creds["secret_key"],
                aws_session_token=iot_creds["token"]
            )
    except Exception as e:
        logger.debug(f"get_boto3_session: IoT script fallback failed: {e}")

    profile_name = aws_config.get("profile") or aws_config.get("aws_profile")
    if profile_name and profile_name != env_profile:
        try:
            session = boto3.Session(profile_name=profile_name)
            logger.debug(f"Initialized AWS profile from config: {profile_name}")
            return session
        except Exception as e:
            logger.debug(f"get_boto3_session: profile from config {profile_name} initialization failed: {e}")
            pass

    return boto3.Session()


def get_active_fargate_tasks(
    session: boto3.Session,
    cluster_name: str = "ScraperCluster",
    service_name: str = "EnrichmentService",
) -> int:
    """Returns the number of running tasks for the specified ECS service."""
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
    stats = get_campaign_stats(campaign_name)
    return {
        "proximity": proximity,
        "locations": stats.get("locations", [])
    }

def get_campaign_stats(campaign_name: str) -> Dict[str, Any]:
    """Collects statistics for a campaign, including local file counts and cloud status."""
    from cocli.core.text_utils import slugify
    import duckdb
    
    stats: Dict[str, Any] = {}
    config = load_campaign_config(campaign_name)
    prospecting_config = config.get("prospecting", {})
    queries = prospecting_config.get("queries", [])
    stats["queries"] = queries

    witness_root = get_cocli_base_dir() / "indexes" / "scraped-tiles"

    stats.update(get_exclusions_data(campaign_name))

    manager = ProspectsIndexManager(campaign_name)
    total_prospects = 0
    source_counts = {"local-worker": 0, "fargate-worker": 0, "unknown": 0}

    if manager.index_dir.exists():
        con = duckdb.connect(database=':memory:')
        checkpoint_path = manager.index_dir / "prospects.checkpoint.usv"
        if checkpoint_path.exists():
            q = f"SELECT count(*), count(CASE WHEN column24 = 'local-worker' THEN 1 END), count(CASE WHEN column24 = 'fargate-worker' THEN 1 END) FROM read_csv('{checkpoint_path}', delim='\x1f', header=False, auto_detect=True, all_varchar=True)"
            res = con.execute(q).fetchone()
            if res:
                total_prospects, source_counts['local-worker'], source_counts['fargate-worker'] = res
                source_counts['unknown'] = total_prospects - source_counts['local-worker'] - source_counts['fargate-worker']

    stats["prospects_count"] = total_prospects
    stats["worker_stats"] = source_counts
    
    aws_config = config.get("aws", {})
    data_bucket = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name")

    if data_bucket:
        stats["using_cloud_queue"] = True
        session = get_boto3_session(config)
        s3 = session.client("s3")
        
        stats["active_fargate_tasks"] = get_active_fargate_tasks(session)

        # 1. S3 Queue Progress
        s3_queues = {}
        for q in ["discovery-gen", "gm-list", "gm-details", "enrichment", "to-call"]:
            try:
                paginator = s3.get_paginator("list_objects_v2")
                pending = 0
                inflight = 0
                prefix_pending = f"campaigns/{campaign_name}/queues/{q}/pending/"
                for page in paginator.paginate(Bucket=data_bucket, Prefix=prefix_pending):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        if key.endswith("task.json") or (q == "discovery-gen" and key.endswith(".usv")):
                            pending += 1
                        elif key.endswith("lease.json"):
                            inflight += 1
                
                completed = 0
                last_completed = None
                prefix_completed = f"campaigns/{campaign_name}/queues/{q}/completed/"
                for page in paginator.paginate(Bucket=data_bucket, Prefix=prefix_completed):
                    for obj in page.get("Contents", []):
                        completed += 1
                        mtime = obj["LastModified"]
                        if last_completed is None or mtime > last_completed:
                            last_completed = mtime
                
                s3_queues[q] = {"pending": pending, "inflight": inflight, "completed": completed, "last_completed_at": last_completed.isoformat() if last_completed else None}
            except Exception as e:
                logger.warning(f"S3 stats failed for {q}: {e}")
        stats["s3_queues"] = s3_queues

        # 2. S3 Worker Heartbeats
        try:
            heartbeats = []
            response = s3.list_objects_v2(Bucket=data_bucket, Prefix="status/")
            for obj in response.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    try:
                        hb_data = s3.get_object(Bucket=data_bucket, Key=obj["Key"])
                        hb_json = json.loads(hb_data["Body"].read().decode("utf-8"))
                        hb_json["last_seen"] = obj["LastModified"].isoformat()
                        heartbeats.append(hb_json)
                    except Exception:
                        continue
            stats["worker_heartbeats"] = heartbeats
        except Exception:
            stats["worker_heartbeats"] = []

    # 3. Local Real-time Gossip Heartbeats
    from .gossip_bridge import bridge
    if bridge and bridge.heartbeats:
        stats["gossip_heartbeats"] = bridge.heartbeats

    # 4. Local Queue Stats
    local_stats = {}
    for q_name in ["discovery-gen", "gm-list", "gm-details", "enrichment", "to-call"]:
        queue_base = paths.queue(campaign_name, q_name)
        q_pending = 0
        q_inflight = 0
        q_completed = 0
        last_completed = None

        p_dir = queue_base / "pending"
        if p_dir.exists():
            for root, dirs, files in os.walk(p_dir):
                for f in files:
                    if f == "task.json" or f.endswith(".usv"):
                        q_pending += 1
                    elif f == "lease.json":
                        q_inflight += 1

        c_dir = queue_base / "completed"
        if c_dir.exists():
            for cf in c_dir.iterdir():
                if cf.suffix in [".json", ".usv"]:
                    q_completed += 1
                    mtime = datetime.fromtimestamp(cf.stat().st_mtime, tz=UTC)
                    if last_completed is None or mtime > last_completed:
                        last_completed = mtime
        
        local_stats[q_name] = {"pending": q_pending, "inflight": q_inflight, "completed": q_completed, "last_completed_at": last_completed.isoformat() if last_completed else None}

    # 5. Mission Index Awareness for local gm-list
    dg_completed = paths.campaign(campaign_name).queue("discovery-gen").completed
    if dg_completed.exists():
        mission_pending = 0
        for tf in dg_completed.glob("**/*.usv"):
            rel_path = tf.relative_to(dg_completed)
            if not (witness_root / rel_path).exists() and not (witness_root / rel_path.with_suffix(".csv")).exists():
                mission_pending += 1
        existing = local_stats.get("gm-list", {}).get("pending", 0)
        if isinstance(existing, (int, float)):
            local_stats["gm-list"]["pending"] = int(existing) + mission_pending
        else:
            local_stats["gm-list"]["pending"] = mission_pending

    stats["local_queues"] = local_stats

    # 6. Legacy compatibility and summarization
    stats["enrichment_pending"] = local_stats["enrichment"]["pending"]
    stats["completed_count"] = local_stats["enrichment"]["completed"]

    # 7. Anomaly and Location stats
    total_scraped_witness = 0
    empty_scraped_witness = 0
    if witness_root.exists():
        for phrase_slug in [slugify(q) for q in queries]:
            for pf in witness_root.glob(f"**/{phrase_slug}.usv"):
                try:
                    with open(pf, "r", encoding="utf-8") as fh:
                        from ..utils.usv_utils import USVDictReader
                        row = next(USVDictReader(fh))
                        total_scraped_witness += 1
                        if int(row.get("items_found", 0)) == 0:
                            empty_scraped_witness += 1
                except Exception:
                    continue
    stats["anomaly_stats"] = {"total_scrapes": total_scraped_witness, "empty_scrapes": empty_scraped_witness}

    return stats
