import boto3
from pathlib import Path

# The 5 Place IDs we are watching
TARGET_IDS = [
    "ChIJ---N6Un5a4cR_bKL7SjsQbI",
    "ChIJ--OPt3FilVQR33FW9tpej2o",
    "ChIJ--iXoKI-KocRHqUqmOJtH3I",
    "ChIJ-0gA9AzbyIARkA7IEsatndM",
    "ChIJ-0xDqDAH2YgRH6qCiA1_Z4Q"
]

def check_status(campaign_name: str = "roadmap") -> None:
    s3 = boto3.client("s3")
    bucket = "roadmap-cocli-data-use1"
    local_base = Path("/home/mstouffer/.local/share/cocli_data")
    
    print(f"Checking status for 5 IDs (Local & S3: {bucket})...")
    print(f"{'Place ID':<30} | {'L-Pend':<6} | {'S3-Pend':<7} | {'S3-Prog':<7} | {'S3-Idx':<6}")
    print("-" * 75)
    
    for pid in TARGET_IDS:
        shard = pid[5] if len(pid) > 5 else "unknown"
        
        # 1. Check Local Pending
        local_pending = local_base / "campaigns" / campaign_name / "queues" / "gm-details" / "pending" / shard / pid / "task.json"
        is_local_pending = local_pending.exists()
        
        # 2. Check S3 Pending
        pending_key = f"queues/gm-details/pending/{shard}/{pid}/task.json"
        is_s3_pending = False
        try:
            s3.head_object(Bucket=bucket, Key=pending_key)
            is_s3_pending = True
        except Exception:
            pass
            
        # 3. Check S3 In-Progress
        in_progress_prefix = f"queues/gm-details/in-progress/{shard}/{pid}/"
        is_in_progress = False
        try:
            resp = s3.list_objects_v2(Bucket=bucket, Prefix=in_progress_prefix)
            if "Contents" in resp:
                is_in_progress = True
        except Exception:
            pass
            
        # 4. Check S3 Index
        index_key = f"campaigns/{campaign_name}/indexes/google_maps_prospects/{shard}/{pid.replace('/', '_')}.usv"
        is_indexed = False
        try:
            s3.head_object(Bucket=bucket, Key=index_key)
            is_indexed = True
        except Exception:
            pass
            
        print(f"{pid:<30} | {str(is_local_pending):<6} | {str(is_s3_pending):<7} | {str(is_in_progress):<7} | {str(is_indexed):<6}")

if __name__ == "__main__":
    check_status()