import logging
import hashlib
import uuid
from typing import List, Optional, Dict
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from ..models.campaign import Campaign
from ..models.website_domain_csv import WebsiteDomainCsv
from ..models.index_manifest import IndexManifest, IndexShard
from ..core.website_domain_csv_manager import CURRENT_SCRAPER_VERSION
from .text_utils import slugdotify

logger = logging.getLogger(__name__)

class S3DomainManager:
    """
    Manages domain index data stored in S3 using a Manifest-Pointer architecture.
    Records are stored as CAS shards, and a manifest tracks the active set.
    """
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
        import os
        self.s3_bucket_name = os.environ.get("COCLI_S3_BUCKET_NAME") or ""
        
        if not self.s3_bucket_name:
            from .config import load_campaign_config
            config = load_campaign_config(self.campaign.name)
            aws_config = config.get("aws", {})
            self.s3_bucket_name = aws_config.get("cocli_data_bucket_name") or f"cocli-data-{self.campaign.name}"

        self.s3_prefix = "indexes/domains/" # Legacy prefix for bootstrapping
        self.shards_prefix = "indexes/shards/"
        self.manifests_prefix = "indexes/manifests/"
        self.latest_pointer_key = "indexes/LATEST"

        try:
            from botocore.config import Config
            session = boto3.Session()
            s3_config: Config = Config(max_pool_connections=50)
            self.s3_client = session.client("s3", config=s3_config)
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise

    def get_latest_manifest(self) -> IndexManifest:
        """Fetches the latest manifest using the LATEST pointer, with bootstrap fallback."""
        try:
            # 1. Read the LATEST pointer
            resp = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=self.latest_pointer_key)
            manifest_key = resp["Body"].read().decode("utf-8").strip()
            
            # 2. Read the manifest content
            resp = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=manifest_key)
            content = resp["Body"].read().decode("utf-8")
            return IndexManifest.from_usv(content)
        except ClientError as e:
            if e.response["Error"]["Code"] in ["NoSuchKey", "404"]:
                # If LATEST is missing, try to bootstrap from legacy USV files
                logger.info("LATEST pointer missing. Attempting to bootstrap manifest from legacy USV files...")
                return self.bootstrap_manifest()
            raise
        except Exception as e:
            logger.error(f"Failed to load latest manifest: {e}")
            return IndexManifest()

    def bootstrap_manifest(self) -> IndexManifest:
        """Creates an initial manifest by scanning the legacy domain USV files."""
        manifest = IndexManifest()
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.s3_bucket_name, Prefix=self.s3_prefix)

            found_legacy = False
            for page in pages:
                for obj in page.get('Contents', []):
                    s3_key = str(obj['Key'])
                    if not s3_key.endswith(".usv") or s3_key.split('/')[-1].startswith("_"):
                        continue
                    
                    found_legacy = True
                    # In legacy mode, domain is derived from filename
                    domain = s3_key.split('/')[-1].replace(".usv", "")
                    
                    # We treat legacy files as Shards directly for the bootstrap
                    manifest.shards[domain] = IndexShard(
                        path=s3_key,
                        schema_version=1, # Assume V1 for legacy
                        updated_at=obj.get('LastModified', datetime.utcnow())
                    )
            
            if found_legacy:
                logger.info(f"Bootstrapped manifest with {len(manifest.shards)} legacy records.")
                # We don't save it yet to avoid accidental writes during a read-only query
            return manifest
        except Exception as e:
            logger.error(f"Manifest bootstrap failed: {e}")
            return manifest

    def add_or_update(self, data: WebsiteDomainCsv) -> None:
        """
        Stores record using CAS and performs an atomic manifest swap.
        """
        if not data.domain:
            return

        # 1. Write the immutable CAS shard
        content = data.to_usv()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        shard_key = f"{self.shards_prefix}{content_hash}.usv"
        
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket_name,
                Key=shard_key,
                Body=content,
                ContentType="text/plain"
            )
        except Exception as e:
            logger.error(f"Failed to write shard {shard_key}: {e}")
            raise

        # 2. Update Manifest (Optimistic Concurrency Control)
        # Note: We use the Manifest-Pointer pattern: generate new manifest, update LATEST.
        max_retries = 3
        for attempt in range(max_retries):
            try:
                manifest = self.get_latest_manifest()
                manifest.shards[str(data.domain)] = IndexShard(
                    path=shard_key,
                    schema_version=data.scraper_version or CURRENT_SCRAPER_VERSION,
                    updated_at=datetime.utcnow()
                )
                manifest.generated_at = datetime.utcnow()
                
                new_manifest_key = f"{self.manifests_prefix}{uuid.uuid4()}.usv"
                self.s3_client.put_object(
                    Bucket=self.s3_bucket_name,
                    Key=new_manifest_key,
                    Body=manifest.to_usv()
                )
                
                # Atomic swap of the LATEST pointer
                self.s3_client.put_object(
                    Bucket=self.s3_bucket_name,
                    Key=self.latest_pointer_key,
                    Body=new_manifest_key
                )
                logger.debug(f"Manifest updated to {new_manifest_key} for domain {data.domain}")
                break
            except Exception as e:
                logger.warning(f"Manifest update attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1:
                    raise

    def query(self, sql_where: str = "") -> List[WebsiteDomainCsv]:
        """
        Queries the global S3 index using DuckDB and the Manifest.
        """
        import duckdb
        manifest = self.get_latest_manifest()
        if not manifest.shards:
            return []

        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        
        session = boto3.Session()
        creds = session.get_credentials()
        con.execute("SET s3_region='us-east-1';")
        if creds:
            frozen = creds.get_frozen_credentials()
            con.execute(f"SET s3_access_key_id='{frozen.access_key}';")
            con.execute(f"SET s3_secret_access_key='{frozen.secret_key}';")
            if frozen.token:
                con.execute(f"SET s3_session_token='{frozen.token}';")

        # Group shards by schema version for Union-by-Name processing
        shards_by_version: Dict[int, List[str]] = {}
        for shard in manifest.shards.values():
            shards_by_version.setdefault(shard.schema_version, []).append(f"s3://{self.s3_bucket_name}/{shard.path}")

        queries = []
        field_names = list(WebsiteDomainCsv.model_fields.keys())
        
        for version, paths in shards_by_version.items():
            # Future: look up columns for specific 'version' if schema changes
            columns = {k: 'VARCHAR' for k in field_names}
            
            # Deduplicate paths to avoid scanning the same compacted file multiple times
            unique_paths = sorted(list(set(paths)))
            path_list = "', '".join(unique_paths)
            
            queries.append(f"""
                SELECT * FROM read_csv(['{path_list}'], 
                    delim='\x1f', 
                    header=False, 
                    quote='', 
                    escape='', 
                    columns={columns},
                    auto_detect=False,
                    union_by_name=True,
                    null_padding=True
                )
            """)

        base_query = " UNION ALL ".join(queries)
        if sql_where:
            base_query = f"SELECT * FROM ({base_query}) WHERE {sql_where}"
            
        try:
            results = con.execute(base_query).fetchall()
            items = []
            for row in results:
                data = dict(zip(field_names, row))
                # Basic fixup for list fields
                if data.get('tags'):
                    data['tags'] = data['tags'].split(';')
                else:
                    data['tags'] = []
                    
                items.append(WebsiteDomainCsv.model_validate(data))
            return items
        except Exception as e:
            logger.error(f"DuckDB S3 Manifest Query failed: {e}")
            return []

    def get_by_domain(self, domain: str) -> Optional[WebsiteDomainCsv]:
        manifest = self.get_latest_manifest()
        shard = manifest.shards.get(domain)
        if not shard:
            return None
            
        try:
            resp = self.s3_client.get_object(Bucket=self.s3_bucket_name, Key=shard.path)
            data = resp["Body"].read().decode("utf-8")
            return WebsiteDomainCsv.from_usv(data)
        except Exception as e:
            logger.error(f"Failed to fetch shard for {domain}: {e}")
            return None

    def get_all_domains_for_campaign(self) -> List[WebsiteDomainCsv]:
        return self.query()

    def _format_tags_for_s3(self, tags: Dict[str, str]) -> str:
        import urllib.parse
        return "&".join([f"{k}={urllib.parse.quote(v)}" for k, v in tags.items()])