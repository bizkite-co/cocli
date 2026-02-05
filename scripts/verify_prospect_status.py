#!/usr/bin/env python3
import boto3
import sys
import os
import argparse
from botocore.exceptions import ClientError
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.core.sharding import get_shard_id
from cocli.core.config import load_campaign_config
from cocli.core.reporting import get_boto3_session

def check_prospect(place_id: str, campaign: str, bucket: str, s3: Any) -> Dict[str, Any]:
    shard = get_shard_id(place_id)
    results = {"place_id": place_id}
    
    # 1. Check Pending
    pending_key = f"campaigns/{campaign}/queues/gm-details/pending/{shard}/{place_id}/task.json"
    try:
        s3.head_object(Bucket=bucket, Key=pending_key)
        results["pending"] = "PENDING"
    except ClientError:
        results["pending"] = "-"

    # 2. Check Lease (In-Progress)
    lease_key = f"campaigns/{campaign}/queues/gm-details/pending/{shard}/{place_id}/lease.json"
    try:
        s3.head_object(Bucket=bucket, Key=lease_key)
        results["lease"] = "ACTIVE"
    except ClientError:
        results["lease"] = "-"

    # 3. Check Completed Queue
    completed_key = f"campaigns/{campaign}/queues/gm-details/completed/{place_id}.json"
    try:
        s3.head_object(Bucket=bucket, Key=completed_key)
        results["completed_queue"] = "DONE"
    except ClientError:
        results["completed_queue"] = "-"

    # 4. Check Index (Unified)
    index_key = f"campaigns/{campaign}/indexes/google_maps_prospects/{place_id}.usv"
    try:
        resp = s3.head_object(Bucket=bucket, Key=index_key)
        size = resp['ContentLength']
        status = "EXISTS"
        if size > 1500:
            status = "HYDRATED"
        elif size > 0:
            status = "HOLLOW"
        results["index"] = f"{status} ({size}b)"
    except ClientError:
        results["index"] = "MISSING"

    return results

def main():
    parser = argparse.ArgumentParser(description="Targeted S3 status verification for Place IDs.")
    parser.add_argument("place_ids", nargs="+", help="One or more Google Place IDs.")
    parser.add_argument("--campaign", "-c", default="roadmap", help="Campaign name.")
    args = parser.parse_args()
    
    config = load_campaign_config(args.campaign)
    aws_config = config.get("aws", {})
    bucket = aws_config.get("data_bucket_name") or f"{args.campaign}-cocli-data-use1"

    session = get_boto3_session(config)
    s3 = session.client("s3")

    print(f"Verifying {len(args.place_ids)} prospects in s3://{bucket}/")
    print(f"{'Place ID':<30} | {'Queue':<8} | {'Lease':<8} | {'Task':<8} | {'Index Status'}")
    print("-" * 85)
    
    for pid in args.place_ids:
        if not pid.startswith("ChIJ"):
            print(f"{pid:<30} | INVALID ID FORMAT")
            continue
        res = check_prospect(pid, args.campaign, bucket, s3)
        print(f"{pid:<30} | {res['pending']:<8} | {res['lease']:<8} | {res['completed_queue']:<8} | {res['index']}")

if __name__ == "__main__":
    main()
