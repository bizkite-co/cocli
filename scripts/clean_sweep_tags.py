import logging
import asyncio
from cocli.core.domain_index_manager import DomainIndexManager
from cocli.models.campaigns.campaign import Campaign

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clean_sweep(campaign_name: str) -> None:
    """
    Sweeps the Manifest index to ensure all domains and tags are clean.
    """
    campaign = Campaign.load(campaign_name)
    s3_manager = DomainIndexManager(campaign)
    
    logger.info(f"Scanning Manifest index for campaign: {campaign_name}")

    manifest = s3_manager.get_latest_manifest()
    if not manifest.shards:
        logger.info("Manifest is empty.")
        return

    # To avoid redundant processing for compacted shards, we group by path
    from typing import Dict, List
    paths_to_domains: Dict[str, List[str]] = {}
    for domain, shard in manifest.shards.items():
        paths_to_domains.setdefault(shard.path, []).append(domain)

    logger.info(f"Auditing {len(paths_to_domains)} unique shards...")

    for path, domains in paths_to_domains.items():
        try:
            resp = s3_manager.s3_client.get_object(Bucket=s3_manager.bucket_name, Key=path)
            content = resp['Body'].read().decode('utf-8')
            
            # Since a shard can contain multiple records (if compacted), we need to handle it.
            # But DomainIndexManager.add_or_update currently handles single records.
            # For a clean sweep, we can just re-process each domain in the shard.
            from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv
            
            # For simplicity in this maintenance script, we'll treat each line as a potential record
            lines = content.strip("\x1e\n").split("\x1e")
            for line in lines:
                if not line.strip():
                    continue
                item = WebsiteDomainCsv.from_usv(line)
                # add_or_update handles CAS write and manifest swap
                s3_manager.add_or_update(item)
                
        except Exception as e:
            logger.error(f"Failed to process shard {path}: {e}")

    logger.info("Clean sweep complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", default="roadmap")
    args = parser.parse_args()
    asyncio.run(clean_sweep(args.campaign))