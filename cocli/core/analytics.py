import logging
import duckdb
from typing import Dict, Any
from .reporting import get_boto3_session
from .config import load_campaign_config
from .utils import UNIT_SEP

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
        "by_machine_scraped": {},
        "total_detailed": 0,
        "total_enriched": 0,
        "total_scraped": 0,
        "mode": "sampled"
    }

    try:
        # 1. Sample GM Details Results (google_maps_prospects/wal/**/*.usv)
        s3 = session.client("s3")
        prefix_det = f"campaigns/{campaign_name}/indexes/google_maps_prospects/wal/"
        res_det = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix_det, MaxKeys=100)
        all_det_objs = res_det.get("Contents", [])
        
        files_csv = [f"s3://{bucket_name}/{obj['Key']}" for obj in all_det_objs if obj["Key"].endswith(".csv")]
        files_usv = [f"s3://{bucket_name}/{obj['Key']}" for obj in all_det_objs if obj["Key"].endswith(".usv")]
        
        # Helper to process a set of files
        def process_files(files: list[str], delimiter: str = ',') -> None:
            if not files:
                return
            path_list = "', '".join(files)
            delim_str = delimiter if delimiter != UNIT_SEP else '\\x1f'
            # Select only processed_by (column 54) to ensure UNION ALL column count matches
            # Using read_csv with explicit column names because files are headerless
            q = f"""
                WITH raw_data AS (
                    SELECT column54 as processed_by 
                    FROM read_csv(['{path_list}'], delim='{delim_str}', header=False, auto_detect=False, columns={{'column54': 'VARCHAR'}}, ignore_errors=True, reject_errors=False)
                    UNION ALL SELECT NULL as processed_by WHERE 1=0
                )
                SELECT processed_by, COUNT(*) as count 
                FROM raw_data
                WHERE processed_by IS NOT NULL AND processed_by != ''
                GROUP BY processed_by
            """
            try:
                for machine, count in con.execute(q).fetchall():
                    stats["by_machine_detailed"][machine] = stats["by_machine_detailed"].get(machine, 0) + count
                    stats["total_detailed"] += count
            except Exception as e:
                logger.debug(f"DuckDB Details query failed for {delim_str}: {e}")

        process_files(files_csv, ',')
        process_files(files_usv, UNIT_SEP)

        # 2. Sample Scrapes (scraped-tiles/**/*.usv and *.csv)
        prefix_scr = f"campaigns/{campaign_name}/indexes/scraped-tiles/"
        res_scr = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix_scr, MaxKeys=100)
        all_scr_objs = res_scr.get("Contents", [])
        
        scr_csv = [f"s3://{bucket_name}/{obj['Key']}" for obj in all_scr_objs if obj["Key"].endswith(".csv")]
        scr_usv = [f"s3://{bucket_name}/{obj['Key']}" for obj in all_scr_objs if obj["Key"].endswith(".usv")]

        def process_scrapes(files: list[str], delimiter: str = ',') -> None:
            if not files:
                return
            path_list = "', '".join(files)
            delim_str = delimiter if delimiter != UNIT_SEP else '\\x1f'
            # Select only processed_by to ensure UNION ALL column count matches
            q = f"""
                WITH raw_data AS (
                    SELECT CAST(processed_by AS VARCHAR) as processed_by FROM read_csv_auto(['{path_list}'], delim='{delim_str}', union_by_name=True, ignore_errors=True, reject_errors=False)
                    UNION ALL SELECT NULL as processed_by WHERE 1=0
                )
                SELECT processed_by, COUNT(*) as count 
                FROM raw_data
                WHERE processed_by IS NOT NULL AND processed_by != ''
                GROUP BY processed_by
            """
            try:
                for machine, count in con.execute(q).fetchall():
                    stats["by_machine_scraped"][machine] = stats["by_machine_scraped"].get(machine, 0) + count
                    stats["total_scraped"] += count
            except Exception as e:
                logger.debug(f"DuckDB Scrapes query failed for {delim_str}: {e}")

        process_scrapes(scr_csv, ',')
        process_scrapes(scr_usv, UNIT_SEP)


        # 3. Sample Enrichment Results (enrichments/website.md)
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
