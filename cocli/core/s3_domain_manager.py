import logging
from typing import List, Optional, Dict
from datetime import datetime # Added import

import boto3
from botocore.exceptions import ClientError

from ..models.campaign import Campaign
from ..models.website_domain_csv import WebsiteDomainCsv
from ..core.website_domain_csv_manager import CURRENT_SCRAPER_VERSION
from .text_utils import slugdotify

logger = logging.getLogger(__name__)

class S3DomainManager:
    """
    Manages domain index data stored in S3.
    Domain records are shared across all campaigns and stored under indexes/domains/.
    Each domain's data is stored as a separate JSON object in S3.
    """
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
        # Determine S3 bucket: env var > campaign config > default
        import os
        self.s3_bucket_name = os.environ.get("COCLI_S3_BUCKET_NAME") or ""
        
        if not self.s3_bucket_name:
            from .config import load_campaign_config
            config = load_campaign_config(self.campaign.name)
            aws_config = config.get("aws", {})
            self.s3_bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{self.campaign.name}"

        if not self.s3_bucket_name:
            raise ValueError(f"S3 bucket name could not be resolved for campaign {self.campaign.name}")

        self.s3_prefix = "indexes/domains/" # Shared resource across all campaigns in this bucket

        try:
            from botocore.config import Config
            session = boto3.Session()
            # Increase pool size to handle concurrent requests without noise
            s3_config: Config = Config(max_pool_connections=50)
            self.s3_client = session.client("s3", config=s3_config)
        except Exception as e:
            logger.error(f"Failed to create S3 client with default credentials: {e}")
            raise

    def _get_s3_key(self, domain: str) -> str:
        """Constructs the S3 key for a given domain, preserving dots and using .usv extension."""
        return f"{self.s3_prefix}{slugdotify(domain)}.usv"

    def get_by_domain(self, domain: str) -> Optional[WebsiteDomainCsv]:
        """
        Fetches a single domain's USV data from S3.
        """
        s3_key = self._get_s3_key(domain)
        try:
            response = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=s3_key)
            data = response["Body"].read().decode("utf-8")
            
            # Use USV parser
            return WebsiteDomainCsv.from_usv(data)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.debug(f"Domain '{domain}' not found in S3 bucket '{self.s3_bucket_name}' under key '{s3_key}'.")
                return None
            logger.error(f"Error fetching domain '{domain}' from S3: {e}")
            raise
        except Exception as e:
            logger.error(f"Error parsing USV data for '{domain}' from S3: {e}")
            return None

    def add_or_update(self, data: WebsiteDomainCsv) -> None:
        """
        Stores or updates a WebsiteDomainCsv object in S3 using USV format.
        """
        if not data.domain:
            logger.warning("Attempted to add/update WebsiteDomainCsv without a domain. Skipping.")
            return

        s3_key = self._get_s3_key(data.domain)
        
        # Always update updated_at before saving
        data.updated_at = datetime.utcnow()
        if not data.scraper_version:
            data.scraper_version = CURRENT_SCRAPER_VERSION

        # Extract metadata to S3 object tags for quick filtering/listing
        s3_tags = {
            'scraper-version': str(data.scraper_version),
            'updated-at': data.updated_at.isoformat(),
            'domain': str(data.domain)
        }
        
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket_name,
                Key=s3_key,
                Body=data.to_usv(),
                ContentType="text/plain", # USV is text
                Tagging=self._format_tags_for_s3(s3_tags)
            )
            logger.debug(f"Successfully added/updated domain '{data.domain}' in S3: {s3_key}")
        except ClientError as e:
            logger.error(f"Error adding/updating domain '{data.domain}' to S3: {e}")
            raise

    def get_all_domains_for_campaign(self) -> List[WebsiteDomainCsv]:
        """
        Lists all domain data for the current campaign from S3.
        """
        domains: List[WebsiteDomainCsv] = []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.s3_bucket_name, Prefix=self.s3_prefix)

            for page in pages:
                for obj in page.get('Contents', []):
                    s3_key = str(obj['Key'])
                    try:
                        response = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=s3_key)
                        data = response["Body"].read().decode("utf-8")
                        domains.append(WebsiteDomainCsv.from_usv(data))
                    except Exception as e:
                        logger.warning(f"Failed to fetch or parse object '{s3_key}' from S3: {e}")
        except ClientError as e:
            logger.error(f"Error listing objects in S3 bucket '{self.s3_bucket_name}' with prefix '{self.s3_prefix}': {e}")
            raise
        return domains

    def query(self, sql_where: str = "") -> List[WebsiteDomainCsv]:
        """
        Queries the global S3 domain index using DuckDB.
        Example: manager.query("ip_address LIKE '23.227.%'") # Shopify IPs
        """
        import duckdb
        
        # Configure DuckDB for S3 access
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        
        # Get credentials from boto3 session
        session = boto3.Session()
        creds = session.get_credentials()
        
        con.execute("SET s3_region='us-east-1';") # Standardize or extract from bucket
        if creds:
            frozen = creds.get_frozen_credentials()
            con.execute(f"SET s3_access_key_id='{frozen.access_key}';")
            con.execute(f"SET s3_secret_access_key='{frozen.secret_key}';")
            if frozen.token:
                con.execute(f"SET s3_session_token='{frozen.token}';")

        usv_glob = f"s3://{self.s3_bucket_name}/{self.s3_prefix}*.usv"
        
        columns = {k: 'VARCHAR' for k in WebsiteDomainCsv.model_fields.keys()}
        
        base_query = f"""
            SELECT * FROM read_csv('{usv_glob}', 
                delim='\\x1f', 
                header=False, 
                quote='', 
                escape='',
                columns={columns}
            )
        """
        
        if sql_where:
            base_query += f" WHERE {sql_where}"
            
        try:
            results = con.execute(base_query).fetchall()
            # Convert tuples back to models
            field_names = list(WebsiteDomainCsv.model_fields.keys())
            items = []
            for row in results:
                data = dict(zip(field_names, row))
                # Basic fixup for list fields
                if data.get('tags'):
                    data['tags'] = data['tags'].split(';')
                items.append(WebsiteDomainCsv.model_validate(data))
            return items
        except Exception as e:
            logger.error(f"DuckDB S3 Query failed: {e}")
            return []

    def _format_tags_for_s3(self, tags: Dict[str, str]) -> str:
        """Formats a dictionary of tags into the URLEncoded string expected by boto3."""
        import urllib.parse
        return "&".join([f"{k}={urllib.parse.quote(v)}" for k, v in tags.items()])
