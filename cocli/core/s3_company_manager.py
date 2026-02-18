import logging
import yaml
from botocore.exceptions import ClientError
from typing import Optional

from .paths import paths
from ..models.campaign import Campaign
from ..models.company import Company # To load/save _index.md equivalent
from ..models.website import Website # To load/save website.md equivalent

logger = logging.getLogger(__name__)

class S3CompanyManager:
    """
    Manages Company and Website data directly in S3, mirroring the local data structure.
    Uses the paths authority to determine S3 keys.
    """
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
        # Determine S3 bucket: env var > campaign config > default
        import os
        from .config import load_campaign_config
        from .reporting import get_boto3_session

        self.s3_bucket_name = os.environ.get("COCLI_S3_BUCKET_NAME") or ""
        config = load_campaign_config(self.campaign.name)

        if not self.s3_bucket_name:
            aws_config = config.get("aws", {})
            self.s3_bucket_name = (
                aws_config.get("data_bucket_name") or 
                aws_config.get("cocli_data_bucket_name") or 
                f"cocli-data-{self.campaign.name}"
            )
        
        if not self.s3_bucket_name:
            raise ValueError(f"S3 bucket name could not be resolved for campaign {self.campaign.name}")

        try:
            from botocore.config import Config
            session = get_boto3_session(config)
            # Increase pool size to handle concurrent requests without noise
            s3_config: Config = Config(max_pool_connections=50)
            self.s3_client = session.client("s3", config=s3_config)
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise

    def _get_s3_key_for_company_index(self, company_slug: str) -> str:
        return paths.s3_company_index(company_slug)

    def _get_s3_key_for_website_enrichment(self, company_slug: str) -> str:
        return paths.s3_website_enrichment(company_slug)

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

    async def fetch_company_index(self, company_slug: str) -> Optional[Company]:
        """Fetches and parses a company index from S3."""
        s3_key = self._get_s3_key_for_company_index(company_slug)
        try:
            response = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            
            # Simple YAML frontmatter parser
            if content.startswith("---"):
                parts = content.split("---")
                if len(parts) >= 3:
                    data = yaml.safe_load(parts[1])
                    return Company.model_validate(data)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            logger.error(f"Error fetching company index from S3 {s3_key}: {e}")
        except Exception as e:
            logger.error(f"Error parsing company index from S3 {s3_key}: {e}")
        return None

    async def fetch_website_enrichment(self, company_slug: str) -> Optional[Website]:
        """Fetches and parses a website enrichment from S3."""
        s3_key = self._get_s3_key_for_website_enrichment(company_slug)
        try:
            response = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            
            if content.startswith("---"):
                parts = content.split("---")
                if len(parts) >= 3:
                    data = yaml.safe_load(parts[1])
                    return Website.model_validate(data)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            logger.error(f"Error fetching website enrichment from S3 {s3_key}: {e}")
        except Exception as e:
            logger.error(f"Error parsing website enrichment from S3 {s3_key}: {e}")
        return None
