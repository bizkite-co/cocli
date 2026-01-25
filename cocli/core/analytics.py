import logging
import duckdb
from typing import Dict, Any
from .reporting import get_boto3_session
from .config import load_campaign_config

logger = logging.getLogger(__name__)

def get_cluster_capacity_stats(campaign_name: str) -> Dict[str, Any]:
    """
    Uses DuckDB to estimate machine distribution by sampling S3 files.
    Full scans are too slow for live reporting (>5 mins for 1.5k+ files).
    """
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name")
    
    if not bucket_name:
        return {"error": "No S3 bucket configured for campaign."}

    session = get_boto3_session(config)
    creds = session.get_credentials()
    if not creds:
        return {"error": "No AWS credentials found."}
    
    frozen = creds.get_frozen_credentials()
    region = aws_config.get("region", "us-east-1")

    # Initialize DuckDB
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")
    con.execute(f"SET s3_region='{region}';")
    con.execute(f"SET s3_access_key_id='{frozen.access_key}';")
    con.execute(f"SET s3_secret_access_key='{frozen.secret_key}';")
    if frozen.token:
        con.execute(f"SET s3_session_token='{frozen.token}';")

    stats: Dict[str, Any] = {
        "by_machine_detailed": {},
        "by_machine_enriched": {},
        "total_detailed": 0,
        "total_enriched": 0,
        "mode": "sampled"
    }

    try:
        # 1. Sample GM Details Results (google_maps_prospects/*.csv)
        s3 = session.client("s3")
        prefix_det = f"campaigns/{campaign_name}/indexes/google_maps_prospects/"
        res_det = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix_det, MaxKeys=100)
        files_det = [f"s3://{bucket_name}/{obj['Key']}" for obj in res_det.get("Contents", []) if obj["Key"].endswith(".csv")]
        
        if files_det:
            path_list = "', '".join(files_det)
            query = f"""
                SELECT processed_by, COUNT(*) as count 
                FROM read_csv_auto(['{path_list}'], union_by_name=True, sample_size=5) 
                WHERE processed_by IS NOT NULL
                GROUP BY processed_by
            """
            results = con.execute(query).fetchall()
            for machine, count in results:
                stats["by_machine_detailed"][machine] = count
                stats["total_detailed"] += count

        # 2. Sample Enrichment Results (enrichments/website.md)
        # website.md files are YAML-frontmatter Markdown. DuckDB can parse these if treated as text,
        # but it's easier to just list them for a count, or if we want attribution, 
        # we'd need to parse the frontmatter. 
        # For now, let's just count the files under the enrichments/ prefix as a proxy for progress.
        # Attribution for enrichment is harder without a full scan.
        # We need to look for **/enrichments/website.md
        # This is slow on S3. Let's use the completed queue folder instead as a proxy.
        prefix_q = f"campaigns/{campaign_name}/queues/enrichment/completed/"
        res_q = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix_q, MaxKeys=100)
        stats["total_enriched_sampled"] = len(res_q.get("Contents", []))
            
    except Exception as e:
        logger.warning(f"DuckDB Sampling failed: {e}")

    return stats

def get_live_progress_stats(campaign_name: str) -> Dict[str, Any]:
    """
    Combines DuckDB analytics with queue counts for a real-time progress view.
    """
    from .reporting import get_campaign_stats
    
    # Get basic stats (Queue counts, local funnel)
    stats = get_campaign_stats(campaign_name)
    
    # Get capacity stats (Work distribution)
    capacity = get_cluster_capacity_stats(campaign_name)
    stats["capacity"] = capacity
    
    return stats
