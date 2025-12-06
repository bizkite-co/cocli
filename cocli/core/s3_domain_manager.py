import json
import logging
from typing import List, Optional, Dict
from datetime import datetime # Added import

import boto3 # type: ignore
from botocore.exceptions import ClientError # type: ignore
from pydantic import ValidationError

from ..models.campaign import Campaign
from ..models.website_domain_csv import WebsiteDomainCsv  # Assuming this model exists
from ..core.website_domain_csv_manager import CURRENT_SCRAPER_VERSION # For scraper_version

logger = logging.getLogger(__name__)

class S3DomainManager:
    """
    Manages domain index data stored in S3 for a specific campaign.
    Each domain's data is stored as a separate JSON object in S3,
    with additional metadata stored in S3 object tags.
    """
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
        # Determine S3 bucket and prefix for the campaign's domain index
        self.s3_bucket_name = "cocli-data-turboship" # Default for domain index

        self.s3_prefix = f"campaigns/{self.campaign.company_slug}/indexes/domains/"

        try:
            session = boto3.Session()
            self.s3_client = session.client("s3")
        except Exception as e:
            logger.error(f"Failed to create S3 client with default credentials: {e}")
            raise

    def _get_s3_key(self, domain: str) -> str:
        """Constructs the S3 key for a given domain."""
        # Domain names often contain characters not friendly for S3 keys or need to be consistent.
        # Use simple slugification or URL encoding if domain can contain special characters.
        # For now, let's assume valid domain names are fine as keys directly appended to prefix.
        return f"{self.s3_prefix}{domain.replace('.', '-')}.json" # Replace dots for easier directory-like management if needed.

    def get_by_domain(self, domain: str) -> Optional[WebsiteDomainCsv]:
        """
        Fetches a single domain's data from S3.
        """
        s3_key = self._get_s3_key(domain)
        try:
            response = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=s3_key)
            data = response["Body"].read().decode("utf-8")
            metadata = response.get("Metadata", {}) # S3 object tags could be here, or use get_object_tagging for full tags.

            # We need to reconstitute WebsiteDomainCsv from data and potentially metadata
            json_data = json.loads(data)
            
            # Reconstitute metadata if it's not part of the JSON payload
            if 'scraper_version' not in json_data and 'scraper-version' in metadata:
                json_data['scraper_version'] = int(metadata['scraper-version'])
            if 'updated_at' not in json_data and 'updated-at' in metadata:
                json_data['updated_at'] = datetime.fromisoformat(metadata['updated-at'])

            return WebsiteDomainCsv.model_validate(json_data)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.debug(f"Domain '{domain}' not found in S3 bucket '{self.s3_bucket_name}' under key '{s3_key}'.")
                return None
            logger.error(f"Error fetching domain '{domain}' from S3: {e}")
            raise
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Error parsing or validating domain data for '{domain}' from S3: {e}")
            return None

    def add_or_update(self, data: WebsiteDomainCsv) -> None:
        """
        Stores or updates a WebsiteDomainCsv object in S3.
        Uses S3 object tags for metadata like scraper_version and updated_at.
        """
        if not data.domain:
            logger.warning("Attempted to add/update WebsiteDomainCsv without a domain. Skipping.")
            return

        s3_key = self._get_s3_key(data.domain)
        
        # Always update updated_at before saving
        data.updated_at = datetime.utcnow()
        if not data.scraper_version:
            data.scraper_version = CURRENT_SCRAPER_VERSION

        # Extract metadata to S3 object tags to avoid reading full object just for metadata.
        # S3 tags are key-value strings. Datetime needs to be ISO formatted.
        s3_tags = {
            'scraper-version': str(data.scraper_version),
            'updated-at': data.updated_at.isoformat()
        }
        
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket_name,
                Key=s3_key,
                Body=json.dumps(data.model_dump(mode='json')),
                ContentType="application/json",
                Tagging=self._format_tags_for_s3(s3_tags)
            )
            logger.debug(f"Successfully added/updated domain '{data.domain}' in S3: {s3_key}")
        except ClientError as e:
            logger.error(f"Error adding/updating domain '{data.domain}' to S3: {e}")
            raise

    def get_all_domains_for_campaign(self) -> List[WebsiteDomainCsv]:
        """
        Lists all domain data for the current campaign from S3.
        This can be slow for many objects and should be used cautiously.
        """
        domains: List[WebsiteDomainCsv] = []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.s3_bucket_name, Prefix=self.s3_prefix)

            for page in pages:
                for obj in page.get('Contents', []):
                    s3_key = str(obj['Key'])
                    try:
                        # Fetch full object and its tags
                        response = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=s3_key)
                        data = response["Body"].read().decode("utf-8")
                        json_data = json.loads(data)
                        
                        tagging_response = self.s3_client.get_object_tagging(Bucket=self.s3_bucket_name, Key=s3_key)
                        tags = {tag['Key']: tag['Value'] for tag in tagging_response.get('TagSet', [])}

                        # Reconstitute metadata that's not in the JSON payload from tags
                        if 'scraper_version' not in json_data and 'scraper-version' in tags:
                            json_data['scraper_version'] = int(tags['scraper-version'])
                        if 'updated_at' not in json_data and 'updated-at' in tags:
                            json_data['updated_at'] = datetime.fromisoformat(tags['updated-at'])

                        domains.append(WebsiteDomainCsv.model_validate(json_data))
                    except ClientError as e:
                        logger.warning(f"Failed to fetch or parse object '{s3_key}' from S3: {e}")
                    except (json.JSONDecodeError, ValidationError) as e:
                        logger.warning(f"Error parsing or validating S3 object '{s3_key}': {e}")
        except ClientError as e:
            logger.error(f"Error listing objects in S3 bucket '{self.s3_bucket_name}' with prefix '{self.s3_prefix}': {e}")
            raise
        return domains

    def _format_tags_for_s3(self, tags: Dict[str, str]) -> str:
        """Formats a dictionary of tags into the URL-encoded string expected by boto3 for S3 object tagging."""
        return "&".join([f"{k}={v}" for k, v in tags.items()])
