import logging
import yaml

import boto3 # type: ignore
from botocore.exceptions import ClientError # type: ignore

from ..models.campaign import Campaign
from ..models.company import Company # To load/save _index.md equivalent
from ..models.website import Website # To load/save website.md equivalent

logger = logging.getLogger(__name__)

class S3CompanyManager:
    """
    Manages Company and Website data directly in S3, mirroring the local cocli_data structure.
    Data is stored in YAML format (similar to local _index.md and website.md).
    """
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
        # Determine S3 bucket and prefix for the campaign's company data
        # Now relying on Task Role for credentials, so profile_name is not needed for session creation
        self.s3_bucket_name = "cocli-data-turboship" # Hardcode for now, or make configurable later
        
        # Base prefix for all companies managed by this campaign
        # e.g., "companies/" or "campaigns/turbo-heat-welding-tools/companies/"
        self.s3_base_prefix = "companies/" # For now, assume top-level companies. Can be refined.

        # If we have a specific campaign company slug, we'll store its data under that slug
        if self.campaign.company_slug:
            self.s3_base_prefix = f"campaigns/{self.campaign.company_slug}/companies/"

        try:
            session = boto3.Session()
            self.s3_client = session.client("s3")
        except Exception as e:
            logger.error(f"Failed to create S3 client with default credentials: {e}")
            raise

    def _get_s3_key_for_company_index(self, company_slug: str) -> str:
        return f"{self.s3_base_prefix}{company_slug}/_index.md"

    def _get_s3_key_for_website_enrichment(self, company_slug: str) -> str:
        return f"{self.s3_base_prefix}{company_slug}/enrichments/website.md"

    async def save_company_index(self, company: Company) -> None:
        if not company.slug:
            logger.warning("Attempted to save company index without a slug.")
            return

        s3_key = self._get_s3_key_for_company_index(company.slug)
        content = f"---\n{yaml.dump(company.model_dump(exclude_none=True))}\n---\n"
        
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket_name,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType="text/markdown"
            )
            logger.debug(f"Successfully saved company index to S3: {s3_key}")
        except ClientError as e:
            logger.error(f"Error saving company index to S3 {s3_key}: {e}")
            raise

    async def save_website_enrichment(self, company_slug: str, website_data: Website) -> None:
        if not company_slug:
            logger.warning("Attempted to save website enrichment without a company slug.")
            return

        s3_key = self._get_s3_key_for_website_enrichment(company_slug)
        content = f"---\n{yaml.dump(website_data.model_dump(exclude_none=True))}\n---\n"

        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket_name,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType="text/markdown"
            )
            logger.debug(f"Successfully saved website enrichment to S3: {s3_key}")
        except ClientError as e:
            logger.error(f"Error saving website enrichment to S3 {s3_key}: {e}")
            raise
