import json
import os

# Centralized sharding logic
def get_shard_id(identifier: str) -> str:
    if not identifier or len(identifier) < 6:
        return "_"
    return identifier[5]

def bulk_re_enqueue(hollow_ids_file: str, bucket: str, campaign: str) -> None:
    from cocli.core.reporting import get_boto3_session
    from cocli.core.config import load_campaign_config
    
    config = load_campaign_config(campaign)
    session = get_boto3_session(config)
    s3 = session.client("s3")
    
    if not os.path.exists(hollow_ids_file):
        print(f"Error: {hollow_ids_file} not found.")
        return

    with open(hollow_ids_file, "r") as f:
        # Assuming USV format where ID is the first unit, or a flat list of IDs
        place_ids = [line.strip().split("\x1f")[0] for line in f if line.strip()]

    print(f"Read {len(place_ids)} IDs from {hollow_ids_file}. Starting bulk sharded enqueue...")
    
    # Batch size for S3 operations if needed, but put_object is individual
    count = 0
    for pid in place_ids:
        # Standard Place ID format: ChIJ...
        if not pid.startswith("ChIJ"):
            continue

        task = {
            "place_id": pid,
            "campaign_name": campaign,
            "force_refresh": True,
            "attempts": 0
        }
        
        shard = get_shard_id(pid)
        key = f"campaigns/{campaign}/queues/gm-details/pending/{shard}/{pid}/task.json"
        
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(task)
            )
            count += 1
            if count % 500 == 0:
                print(f"Enqueued {count} / {len(place_ids)} tasks...")
        except Exception as e:
            print(f"Error enqueuing {pid}: {e}")

    print(f"Finished. Enqueued {count} tasks to s3://{bucket}/...")

if __name__ == "__main__":
    import sys
    from cocli.core.config import load_campaign_config
    CAMPAIGN = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    config = load_campaign_config(CAMPAIGN)
    aws_config = config.get("aws", {})
    BUCKET = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name") or f"{CAMPAIGN}-cocli-data-use1"
    HOLLOW_FILE = f"/home/mstouffer/.local/share/cocli_data/campaigns/{CAMPAIGN}/recovery/hollow_place_ids.usv"
    bulk_re_enqueue(HOLLOW_FILE, BUCKET, CAMPAIGN)
