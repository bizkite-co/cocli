import asyncio
import logging
from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager
from cocli.core.s3_domain_manager import S3DomainManager
from cocli.models.campaign import Campaign
from cocli.core.config import load_campaign_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def sync_to_s3(campaign_name: str) -> None:
    config_data = load_campaign_config(campaign_name)
    
    # Merge relevant sections for the Campaign model
    full_campaign_data = {}
    if "campaign" in config_data:
        full_campaign_data.update(config_data["campaign"])
    
    # Add other required sections
    for key in ["google_maps", "prospecting", "aws"]:
        if key in config_data:
            full_campaign_data[key] = config_data[key]
            
    # Ensure name is set correctly
    if "name" not in full_campaign_data:
        full_campaign_data["name"] = campaign_name
        
    campaign = Campaign(**full_campaign_data)
    
    s3_manager = S3DomainManager(campaign=campaign)
    local_manager = WebsiteDomainCsvManager()
    
    print(f"Syncing {len(local_manager.data)} domains to S3 bucket: {s3_manager.s3_bucket_name}")
    
    count = 0
    for domain, item in local_manager.data.items():
        try:
            s3_manager.add_or_update(item)
            count += 1
            if count % 100 == 0:
                print(f"Uploaded {count} domains...")
        except Exception as e:
            logger.error(f"Failed to upload {domain}: {e}")
            
    print(f"Successfully synced {count} domains to S3.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    args = parser.parse_args()
    
    asyncio.run(sync_to_s3(args.campaign))
