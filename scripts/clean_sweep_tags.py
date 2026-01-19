import logging
import asyncio
from cocli.core.s3_domain_manager import S3DomainManager
from cocli.models.website_domain_csv import WebsiteDomainCsv
from cocli.models.campaign import Campaign

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clean_sweep(campaign_name: str) -> None:
    """
    Sweeps the Atomic USV index to ensure all domains and tags are clean.
    """
    campaign = Campaign.load(campaign_name)
    s3_manager = S3DomainManager(campaign)
    bucket_name = s3_manager.s3_bucket_name
    
    logger.info(f"Scanning Atomic USV index in bucket: {bucket_name}")

    paginator = s3_manager.s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix="indexes/domains/")

    tasks = []
    semaphore = asyncio.Semaphore(50)

    async def check_item(key: str) -> None:
        async with semaphore:
            loop = asyncio.get_event_loop()
            def process() -> None:
                resp = s3_manager.s3_client.get_object(Bucket=bucket_name, Key=key)
                content = resp['Body'].read().decode('utf-8')
                
                # Re-loading into model will trigger the new robust validator
                item = WebsiteDomainCsv.from_usv(content)
                
                # Check if the domain in the content is different from the key
                # Or if the key is just plain wrong
                current_key = key.split("/")[-1]
                correct_key = f"{s3_manager._get_s3_key(str(item.domain)).split('/')[-1]}"
                
                if current_key != correct_key:
                    logger.info(f"Renaming dirty key: {current_key} -> {correct_key}")
                    s3_manager.add_or_update(item)
                    s3_manager.s3_client.delete_object(Bucket=bucket_name, Key=key)
                else:
                    # Key is correct, but let's re-save to ensure Tags are clean
                    s3_manager.add_or_update(item)

            await loop.run_in_executor(None, process)

    for page in pages:
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith(".usv") and not key.split("/")[-1].startswith("_"):
                tasks.append(check_item(key))

    if tasks:
        logger.info(f"Auditing {len(tasks)} items...")
        await asyncio.gather(*tasks)
    
    logger.info("Clean sweep complete.")

if __name__ == "__main__":
    asyncio.run(clean_sweep("roadmap"))
