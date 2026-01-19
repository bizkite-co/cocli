import json
import logging
import asyncio
from cocli.core.s3_domain_manager import S3DomainManager
from cocli.models.website_domain_csv import WebsiteDomainCsv
from cocli.models.campaign import Campaign

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_item(s3_manager: S3DomainManager, bucket_name: str, old_key: str, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        try:
            # We use threading for boto3 since it's not async-native, 
            # but semaphore limits the concurrency
            loop = asyncio.get_event_loop()
            
            def process() -> str:
                resp = s3_manager.s3_client.get_object(Bucket=bucket_name, Key=old_key)
                content = resp['Body'].read().decode('utf-8')
                data = json.loads(content)
                
                # Reconstitute model (Skip strict validation for anomalous emails during migration)
                try:
                    item = WebsiteDomainCsv.model_validate(data)
                except Exception:
                    # Fallback: manually construct model to bypass email validation if it fails
                    # but keep most data
                    data['email'] = None 
                    item = WebsiteDomainCsv.model_construct(**data)
                
                # add_or_update now uses USV and the .usv extension
                s3_manager.add_or_update(item)
                
                # Delete old JSON key
                s3_manager.s3_client.delete_object(Bucket=bucket_name, Key=old_key)
                return str(item.domain)

            domain = await loop.run_in_executor(None, process)
            logger.info(f"Migrated: {domain}")

        except Exception as e:
            logger.error(f"Failed to migrate {old_key}: {e}")

async def migrate_to_usv(campaign_name: str, source_prefix: str) -> None:
    """
    Migrates S3 domain index objects from JSON to USV format with parallelism.
    """
    campaign = Campaign.load(campaign_name)
    s3_manager = S3DomainManager(campaign)
    
    bucket_name = s3_manager.s3_bucket_name
    
    logger.info(f"Scanning {source_prefix} in bucket: {bucket_name}")

    paginator = s3_manager.s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=source_prefix)

    tasks = []
    semaphore = asyncio.Semaphore(50) # Process 50 files at once

    for page in pages:
        for obj in page.get('Contents', []):
            old_key = obj['Key']
            if old_key.endswith(".json"):
                tasks.append(migrate_item(s3_manager, bucket_name, old_key, semaphore))

    if not tasks:
        logger.info("No JSON files found to migrate.")
        return

    logger.info(f"Starting parallel migration of {len(tasks)} items...")
    await asyncio.gather(*tasks)
    logger.info("S3 Migration to Atomic USV complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--source-prefix", default="indexes/domains/")
    args = parser.parse_args()

    asyncio.run(migrate_to_usv(args.campaign, args.source_prefix))
