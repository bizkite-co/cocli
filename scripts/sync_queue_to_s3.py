import boto3
from pathlib import Path

TARGET_IDS = [
    "ChIJ---N6Un5a4cR_bKL7SjsQbI",
    "ChIJ--OPt3FilVQR33FW9tpej2o",
    "ChIJ--iXoKI-KocRHqUqmOJtH3I",
    "ChIJ-0gA9AzbyIARkA7IEsatndM",
    "ChIJ-0xDqDAH2YgRH6qCiA1_Z4Q"
]

def sync_to_s3(campaign_name: str = "roadmap") -> None:
    s3 = boto3.client("s3")
    bucket = "roadmap-cocli-data-use1"
    local_base = Path("/home/mstouffer/.local/share/cocli_data")
    
    for pid in TARGET_IDS:
        shard = pid[5] if len(pid) > 5 else "unknown"
        local_path = local_base / "queues" / campaign_name / "gm-details" / "pending" / shard / pid / "task.json"
        
        if local_path.exists():
            s3_key = f"queues/gm-details/pending/{shard}/{pid}/task.json"
            print(f"Pushing {pid} to s3://{bucket}/{s3_key}")
            with open(local_path, "rb") as f:
                s3.put_object(Bucket=bucket, Key=s3_key, Body=f)
        else:
            print(f"Warning: Local file not found for {pid}: {local_path}")

if __name__ == "__main__":
    sync_to_s3()
