import boto3
import logging
import argparse
from typing import Any
from botocore.exceptions import ClientError
from rich.console import Console
from rich.progress import track

console = Console()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("S3Migrator")

def get_s3_client(profile_name: str) -> Any:
    session = boto3.Session(profile_name=profile_name)
    return session.client("s3")

def move_objects(s3: Any, bucket: str, source_prefix: str, dest_prefix: str, dry_run: bool = False) -> None:
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=source_prefix)

    objects_to_move = []
    for page in pages:
        if "Contents" in page:
            for obj in page["Contents"]:
                objects_to_move.append(obj["Key"])

    if not objects_to_move:
        console.print(f"[yellow]No objects found in {source_prefix}[/yellow]")
        return

    console.print(f"Found {len(objects_to_move)} objects to move from {source_prefix} to {dest_prefix}")

    for key in track(objects_to_move, description=f"Moving {source_prefix}..."):
        relative_path = key[len(source_prefix):]
        new_key = dest_prefix + relative_path
        
        if dry_run:
            logger.info(f"[DRY RUN] Would move {key} -> {new_key}")
            continue

        try:
            # Copy
            copy_source = {'Bucket': bucket, 'Key': key}
            s3.copy_object(Bucket=bucket, CopySource=copy_source, Key=new_key)
            # Delete
            s3.delete_object(Bucket=bucket, Key=key)
            logger.info(f"Moved {key} -> {new_key}")
        except ClientError as e:
            logger.error(f"Error moving {key}: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate S3 paths to conform to Directory Data Structure.")
    parser.add_argument("--bucket", required=True, help="S3 Bucket Name")
    parser.add_argument("--profile", default="default", help="AWS Profile")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the migration")
    args = parser.parse_args()

    s3 = get_s3_client(args.profile)
    bucket = args.bucket

    # 1. Move companies from campaign-specific path to root companies/
    # Source: campaigns/turbo-heat-welding-tools/companies/
    # Dest: companies/
    source_companies = "campaigns/turbo-heat-welding-tools/companies/"
    dest_companies = "companies/"
    move_objects(s3, bucket, source_companies, dest_companies, args.dry_run)

    # 2. Move indexes from campaign-specific path to root indexes/
    # Source: campaigns/turbo-heat-welding-tools/indexes/
    # Dest: indexes/
    source_indexes = "campaigns/turbo-heat-welding-tools/indexes/"
    dest_indexes = "indexes/"
    move_objects(s3, bucket, source_indexes, dest_indexes, args.dry_run)
    
    # 3. Cleanup empty folder if possible (S3 doesn't have real folders, but we can check)
    # The 'campaigns/turbo-heat-welding-tools/' prefix should now be effectively empty of the migrated data.

    console.print("[bold green]Migration Complete![/bold green]")

if __name__ == "__main__":
    main()
