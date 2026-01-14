import boto3
import argparse
import logging
from typing import Any

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def migrate_queue(campaign: str, queue: str, bucket: str, s3_client: Any, dry_run: bool = False) -> None:
    base_prefix = f"campaigns/{campaign}/queues/{queue}/pending/"
    logger.info(f"Scanning s3://{bucket}/{base_prefix}...")

    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=base_prefix)

    total_moved = 0
    
    for page in pages:
        if 'Contents' not in page:
            continue

        for obj in page['Contents']:
            key = obj['Key']
            # Relative path after .../pending/
            rel_path = key[len(base_prefix):]
            
            # parts: [task_id_dir, filename] OR [shard, task_id_dir, filename]
            parts = rel_path.split('/')
            
            # If parts[0] is not a single character, it's the old flat structure
            # (Note: task_id_dirs are hashes or coordinates, always > 1 char)
            if len(parts[0]) > 1:
                task_id = parts[0]
                filename = parts[1] if len(parts) > 1 else ""
                
                if not filename:
                    continue # Skip directory markers if any
                
                shard = task_id[0]
                new_key = f"{base_prefix}{shard}/{rel_path}"
                
                logger.info(f"{'[DRY RUN] ' if dry_run else ''}Moving {key} -> {new_key}")
                total_moved += 1
                
                if not dry_run:
                    try:
                        # Copy to new location
                        s3_client.copy_object(
                            Bucket=bucket,
                            CopySource={'Bucket': bucket, 'Key': key},
                            Key=new_key
                        )
                        # Delete old location
                        s3_client.delete_object(Bucket=bucket, Key=key)
                    except Exception as e:
                        logger.error(f"Failed to move {key}: {e}")
                        total_moved -= 1
            else:
                logger.debug(f"Skipping already sharded key: {key}")

    logger.info(f"Migration complete for {queue}. Total moved: {total_moved}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Filesystem Queue from flat to sharded structure in S3.")
    parser.add_argument("--campaign", required=True, help="Campaign name")
    parser.add_argument("--bucket", help="S3 Bucket name (overrides config)")
    parser.add_argument("--profile", help="AWS Profile")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be moved without doing it")
    
    args = parser.parse_args()

    # Resolve bucket from config if not provided
    bucket = args.bucket
    if not bucket:
        from cocli.core.config import load_campaign_config
        config = load_campaign_config(args.campaign)
        bucket = config.get("aws", {}).get("cocli_data_bucket_name") or f"cocli-data-{args.campaign}"

    session = boto3.Session(profile_name=args.profile)
    s3 = session.client("s3")

    queues = ["gm-list", "gm-details", "enrichment"]
    
    for q in queues:
        migrate_queue(args.campaign, q, bucket, s3, args.dry_run)

if __name__ == "__main__":
    main()