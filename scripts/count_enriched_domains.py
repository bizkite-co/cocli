import boto3
from datetime import datetime, timezone, timedelta
from cocli.core.config import load_campaign_config, get_campaign

def main() -> None:
    campaign_name = get_campaign()
    if not campaign_name:
        print("No campaign specified.")
        return

    print(f"Counting enriched domains for campaign: {campaign_name}...")
    
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{campaign_name}"
    
    # We need to look at indexes/domains/ (which is the new shared path)
    # AND potentially the old path if some workers are still using it? 
    # But I patched the code to use indexes/domains/.
    
    # Wait, check cocli/core/domain_index_manager.py again.
    # It uses "indexes/domains/" as prefix.
    
    prefix = "indexes/domains/"
    
    session = boto3.Session(profile_name=aws_config.get("profile"))
    s3 = session.client("s3")
    
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    
    total_count = 0
    recent_count_24h = 0
    recent_count_72h = 0
    now = datetime.now(timezone.utc)
    
    print(f"Scanning s3://{bucket_name}/{prefix}...")
    
    for page in pages:
        if "Contents" in page:
            for obj in page["Contents"]:
                total_count += 1
                last_modified = obj["LastModified"]
                
                age = now - last_modified
                if age < timedelta(hours=24):
                    recent_count_24h += 1
                if age < timedelta(hours=72):
                    recent_count_72h += 1
    
    print(f"\nTotal Enriched Domains in Index: {total_count}")
    print(f"Enriched in last 24 hours: {recent_count_24h}")
    print(f"Enriched in last 72 hours: {recent_count_72h}")

if __name__ == "__main__":
    main()
