import json
import logging
import asyncio
import boto3
from botocore.config import Config
from cocli.core.config import load_campaign_config
from cocli.core.text_utils import slugdotify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_s3_keys(campaign_name: str, profile: str, source_prefix: str = "indexes/domains/") -> None:
    """
    Migrates S3 domain index keys from old formats to new dot-format.
    Supports:
    - indexes/domains/example-com.json -> indexes/domains/example.com.json
    - indexes/domains/example-com/search.json -> indexes/domains/example.com.json
    """
    config_data = load_campaign_config(campaign_name)
    aws_config = config_data.get("aws", {})
    bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{campaign_name}"
    target_prefix = "indexes/domains/"

    session = boto3.Session(profile_name=profile)
    s3 = session.client("s3", config=Config(max_pool_connections=50))

    logger.info(f"Starting migration from {source_prefix} to {target_prefix} in bucket: {bucket_name}")

    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=source_prefix)

    for page in pages:
        for obj in page.get('Contents', []):
            old_key = obj['Key']
            
            # Handle both .json files and search.json inside directories
            if not old_key.endswith(".json"):
                continue

            try:
                resp = s3.get_object(Bucket=bucket_name, Key=old_key)
                data = json.loads(resp['Body'].read().decode('utf-8'))
                domain = data.get('domain')

                if not domain:
                    logger.warning(f"No domain found in {old_key}, skipping.")
                    continue

                new_key = f"{target_prefix}{slugdotify(domain)}.json"

                if old_key == new_key:
                    logger.info(f"Key {old_key} is already correct and in the right place.")
                    continue

                logger.info(f"Migrating: {old_key} -> {new_key}")

                # Copy to new key
                s3.copy_object(
                    Bucket=bucket_name,
                    CopySource={'Bucket': bucket_name, 'Key': old_key},
                    Key=new_key
                )
                
                # Delete old key
                s3.delete_object(Bucket=bucket_name, Key=old_key)

            except Exception as e:
                logger.error(f"Failed to migrate {old_key}: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--source-prefix", default="indexes/domains/")
    args = parser.parse_args()

    asyncio.run(migrate_s3_keys(args.campaign, args.profile, args.source_prefix))
