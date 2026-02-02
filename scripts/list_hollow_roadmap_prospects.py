import boto3
import sys
import os
import csv
from io import StringIO

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from cocli.utils.usv_utils import USVDictReader

def list_hollow_prospects(bucket: str, prefix: str, output_path: str) -> None:
    s3 = boto3.Session(profile_name="westmonroe-support").client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    
    hollow_pids = []
    count = 0
    print(f"Scanning s3://{bucket}/{prefix}...")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".usv"):
                continue
            
            count += 1
            if count % 1000 == 0:
                print(f"  Processed {count} files...")

            # Fast size-based filter: Hollow files are usually < 1KB
            if obj["Size"] > 1500:
                continue

            # Confirm by reading
            response = s3.get_object(Bucket=bucket, Key=obj["Key"])
            content = response["Body"].read().decode("utf-8")
            reader = USVDictReader(StringIO(content))
            rows = list(reader)
            if not rows:
                continue
            
            row = rows[0]
            name = row.get("Name") or row.get("name")
            slug = row.get("company_slug") or row.get("Company_Slug")
            pid = row.get("Place_ID") or row.get("place_id")
            
            if not name or not slug or name == "None":
                if pid:
                    hollow_pids.append(pid)
                else:
                    # Try to extract PID from filename if header is broken
                    filename = os.path.basename(obj["Key"]).replace(".usv", "")
                    if filename.startswith("ChI"):
                        hollow_pids.append(filename)

    print(f"Found {len(hollow_pids)} hollow prospects out of {count} files.")
    
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["place_id"])
        for pid in hollow_pids:
            writer.writerow([pid])
    
    print(f"List saved to {output_path}")

if __name__ == "__main__":
    BUCKET = "roadmap-cocli-data-use1"
    PREFIX = "campaigns/roadmap/indexes/google_maps_prospects/"
    OUTPUT = "/home/mstouffer/.local/share/cocli_data/campaigns/roadmap/recovery/hollow_place_ids.csv"
    list_hollow_prospects(BUCKET, PREFIX, OUTPUT)
