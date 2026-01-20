import logging
import asyncio
import time
import uuid
import os
from typing import Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from cocli.core.s3_domain_manager import S3DomainManager
from cocli.models.campaign import Campaign
from cocli.models.index_manifest import IndexShard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_shard(s3_client: Any, bucket: str, key: str) -> Optional[str]:
    try:
        resp = s3_client.get_object(Bucket=bucket, Key=key)
        content = resp["Body"].read().decode("utf-8")
        return str(content)
    except Exception as e:
        logger.warning(f"Failed to download {key}: {e}")
        return None

async def compact(campaign_name: str) -> None:
    campaign = Campaign.load(campaign_name)
    s3_manager = S3DomainManager(campaign)
    
    logger.info("Loading latest manifest for compaction...")
    manifest = s3_manager.get_latest_manifest()
    
    if not manifest.shards:
        logger.warning("Manifest is empty.")
        return

    compaction_id = str(uuid.uuid4())
    compacted_key = f"{s3_manager.shards_prefix}compacted-{compaction_id}.usv"
    local_temp = f"/tmp/{compaction_id}.usv"
    
    logger.info(f"Merging {len(manifest.shards)} shards into {compacted_key} using ThreadPoolExecutor...")
    
    start_time = time.time()
    
    # We use a ThreadPool for I/O bound S3 downloads
    keys = [shard.path for shard in manifest.shards.values()]
    
    with open(local_temp, "w", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=50) as executor:
            # We process in batches to avoid memory overload
            batch_size = 500
            for i in range(0, len(keys), batch_size):
                batch = keys[i:i+batch_size]
                results = list(executor.map(lambda k: download_shard(s3_manager.s3_client, s3_manager.s3_bucket_name, k), batch))
                
                for content in results:
                    if content:
                        # Ensure content ends with newline if not already
                        if not content.endswith("\n"):
                            content += "\n"
                        f.write(content)
                
                logger.info(f"Processed {min(i+batch_size, len(keys))}/{len(keys)} shards...")

    logger.info(f"Uploading compacted file ({os.path.getsize(local_temp) / 1024:.2f} KB) to S3...")
    s3_manager.s3_client.upload_file(local_temp, s3_manager.s3_bucket_name, compacted_key)
    
    logger.info("Updating manifest pointers...")
    new_shard = IndexShard(
        path=compacted_key,
        schema_version=6,
        updated_at=datetime.utcnow()
    )
    
    for domain in manifest.shards:
        manifest.shards[domain] = new_shard
        
    manifest_key = f"{s3_manager.manifests_prefix}{uuid.uuid4()}.usv"
    s3_manager.s3_client.put_object(
        Bucket=s3_manager.s3_bucket_name,
        Key=manifest_key,
        Body=manifest.to_usv()
    )
    
    s3_manager.s3_client.put_object(
        Bucket=s3_manager.s3_bucket_name,
        Key=s3_manager.latest_pointer_key,
        Body=manifest_key
    )
    
    duration = time.time() - start_time
    logger.info(f"Compaction complete in {duration:.2f} seconds.")
    
    if os.path.exists(local_temp):
        os.remove(local_temp)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    args = parser.parse_args()
    asyncio.run(compact(args.campaign))