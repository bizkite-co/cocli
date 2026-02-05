import sys
import os
import argparse
from typing import Dict, Any, Optional
from pathlib import Path
from io import StringIO

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.models.google_maps_raw import GoogleMapsRawResult
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader

def load_google_maps_usv_cache(cache_path: Path) -> Dict[str, Dict[str, Any]]:
    """Loads the local USV cache as a dictionary indexed by Place ID."""
    cache = {}
    if not cache_path.exists():
        print(f"Warning: Cache file {cache_path} not found.")
        return cache

    print(f"Loading local cache from {cache_path}...")
    with open(cache_path, "r", encoding="utf-8") as f:
        reader = USVDictReader(f)
        for row in reader:
            # Check both internal snake_case and raw PascalCase
            pid = row.get("place_id") or row.get("Place_ID")
            if pid:
                cache[pid] = row
    print(f"Loaded {len(cache)} items from cache.")
    return cache

def repopulate_prospect_metadata_from_cache_row(
    hollow_row: Dict[str, Any], 
    cache: Dict[str, Dict[str, Any]]
) -> Optional[GoogleMapsProspect]:
    """
    Takes a hollow prospect row and attempts to fill missing attributes 
    (Name, City, Zip, etc.) using a matching entry from the local cache.
    """
    pid = hollow_row.get("Place_ID") or hollow_row.get("place_id")
    if not pid:
        return None
    
    cache_row = cache.get(pid)
    if not cache_row:
        return None
    
    # Map cache_row keys to GoogleMapsRawResult fields
    raw_data = {}
    raw_fields = GoogleMapsRawResult.model_fields.keys()
    
    for field in raw_fields:
        # Check PascalCase (raw), then snake_case (internal)
        val = cache_row.get(field)
        if val is None:
            val = cache_row.get(field.lower())
        
        # Specific overrides for numeric types that might be empty strings
        if field in ["Reviews_count"] and val == "":
            val = None
        if field in ["Average_rating", "Latitude", "Longitude"] and val == "":
            val = None
        
        raw_data[field] = val

    # Ensure Place_ID is set correctly for the model
    raw_data["Place_ID"] = pid
    
    try:
        raw_obj = GoogleMapsRawResult(**raw_data)
        return GoogleMapsProspect.from_raw(raw_obj)
    except Exception as e:
        print(f"Error transforming {pid}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Repopulate roadmap metadata from local cache.")
    parser.add_argument("--limit", type=int, default=10, help="Number of records to process (1, 3, 10 rule).")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    parser.add_argument("--campaign", default="roadmap", help="Campaign name.")
    args = parser.parse_args()

    from cocli.core.reporting import get_boto3_session
    from cocli.core.config import load_campaign_config
    
    config = load_campaign_config(args.campaign)
    aws_config = config.get("aws", {})
    bucket = aws_config.get("data_bucket_name") or f"{args.campaign}-cocli-data-use1"

    # Use robust session resolution
    session = get_boto3_session(config)
    s3 = session.client("s3")
    
    cache_path = Path("/home/mstouffer/.local/share/cocli_data/cache/google_maps_cache.usv")
    cache = load_google_maps_usv_cache(cache_path)

    prefix = f"campaigns/{args.campaign}/indexes/google_maps_prospects/"
    paginator = s3.get_paginator("list_objects_v2")
    
    files_to_check = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".usv") or obj["Key"].endswith(".csv"):
                files_to_check.append(obj["Key"])
                if len(files_to_check) >= args.limit:
                    break
        if len(files_to_check) >= args.limit:
            break

    print(f"Auditing {len(files_to_check)} files for missing metadata in {bucket}...")
    
    repopulated_count = 0
    for key in files_to_check:
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")
        
        reader = USVDictReader(StringIO(content))
        rows = list(reader)
        if not rows:
            continue
        
        row = rows[0]
        # Identity Check: Is it missing Name or City?
        name = row.get("Name") or row.get("name")
        city = row.get("City") or row.get("city")
        
        if not name or not city or name == "None" or city == "None":
            pid = row.get("Place_ID") or row.get("place_id")
            print(f"Hollow record: {pid} ({key})")
            
            repopulated = repopulate_prospect_metadata_from_cache_row(row, cache)
            if repopulated:
                print(f"  [REPOPULATED] {repopulated.name} in {repopulated.city}, {repopulated.state}")
                repopulated_count += 1
                
                if not args.dry_run:
                    new_content = repopulated.to_usv()
                    s3.put_object(Bucket=bucket, Key=key, Body=new_content.encode("utf-8"))
            else:
                print(f"  [STILL HOLLOW] No cache entry for {pid}")

    print(f"\nSummary: Checked {len(files_to_check)}, Repopulated {repopulated_count}")

if __name__ == "__main__":
    main()