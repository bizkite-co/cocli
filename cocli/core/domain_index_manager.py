import logging
import os
import boto3
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from botocore.config import Config

from ..models.campaigns.campaign import Campaign
from ..models.campaigns.indexes.domains import WebsiteDomainCsv
from ..models.index_manifest import IndexManifest, IndexShard
from .text_utils import slugdotify
from .config import get_cocli_base_dir

logger = logging.getLogger(__name__)

class DomainIndexManager:
    """
    Unified manager for domain index data.
    Supports both S3 (distributed) and Local Filesystem storage.
    Uses a Manifest-Pointer architecture for atomic updates and DuckDB for fast querying.
    """
    def __init__(self, campaign: Campaign, use_cloud: bool = False):
        self.campaign = campaign
        
        # Resolve bucket name for later use (syncing)
        from .config import load_campaign_config
        config = load_campaign_config(self.campaign.name)
        aws_config = config.get("aws", {})
        self.bucket_name = os.environ.get("COCLI_S3_BUCKET_NAME") or aws_config.get("data_bucket_name")
        
        self.is_cloud = use_cloud
        
        if self.is_cloud:
            self.base_prefix = "" # Root of bucket
            self.protocol = "s3://"
            self._init_s3_client(aws_config)
            # Common Path Components (Nested within domains/)
            self.inbox_root = "indexes/domains/inbox/"
            self.shards_prefix = "indexes/domains/shards/"
            self.manifests_prefix = "indexes/domains/manifests/"
            self.latest_pointer_key = "indexes/domains/LATEST"
        else:
            self.is_cloud = False
            # Domains are global shared data
            self.root_dir = get_cocli_base_dir() / "indexes" / "domains"
            self.root_dir.mkdir(parents=True, exist_ok=True)
            self.protocol = "" # Local paths are absolute or relative to CWD
            
            # Local components are relative to the domain-specific root
            self.inbox_root = "inbox/"
            self.shards_prefix = "shards/"
            self.manifests_prefix = "manifests/"
            self.latest_pointer_key = "LATEST"

    def _init_s3_client(self, aws_config: Dict[str, Any]) -> None:
        try:
            from .reporting import get_boto3_session
            
            # Prepare config structure for get_boto3_session
            config = {
                "aws": aws_config,
                "campaign": {"name": self.campaign.name}
            }
            session = get_boto3_session(config)
            
            s3_config = Config(max_pool_connections=50)
            self.s3_client = session.client("s3", config=s3_config)
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise

    def _get_path(self, key: str) -> str:
        if self.is_cloud:
            return f"{self.protocol}{self.bucket_name}/{key}"
        else:
            return str(self.root_dir / key)

    def _read_object(self, key: str) -> str:
        if self.is_cloud:
            resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return resp["Body"].read().decode("utf-8")
        else:
            path = self.root_dir / key
            return path.read_text(encoding="utf-8")

    def _write_object(self, key: str, content: str) -> None:
        if self.is_cloud:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content,
                ContentType="text/plain"
            )
        else:
            path = self.root_dir / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _delete_object(self, key: str) -> None:
        if self.is_cloud:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
        else:
            path = self.root_dir / key
            if path.exists():
                path.unlink()

    def _exists(self, key: str) -> bool:
        if self.is_cloud:
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
                return True
            except Exception:
                return False
        else:
            return (self.root_dir / key).exists()

    def get_shard_id(self, domain: str) -> str:
        """Calculates a deterministic shard ID (00-ff) based on domain hash."""
        return hashlib.sha256(domain.encode()).hexdigest()[:2]

    def get_latest_manifest(self) -> IndexManifest:
        """Fetches the latest manifest using the LATEST pointer."""
        try:
            manifest_key = self._read_object(self.latest_pointer_key).strip()
            content = self._read_object(manifest_key)
            return IndexManifest.from_usv(content)
        except Exception as e:
            # Fallback to bootstrap if pointer is missing
            logger.info(f"LATEST pointer missing or unreadable ({e}). Attempting bootstrap...")
            return self.bootstrap_manifest()

    def bootstrap_manifest(self) -> IndexManifest:
        """Creates an initial manifest by scanning the shards directory."""
        manifest = IndexManifest()
        try:
            if self.is_cloud:
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.shards_prefix)
                for page in pages:
                    for obj in page.get('Contents', []):
                        key = str(obj['Key'])
                        filename = key.split('/')[-1]
                        if not filename.endswith(".usv") or filename.startswith("_"):
                            continue
                        shard_id = filename.replace(".usv", "")
                        manifest.shards[shard_id] = IndexShard(path=key, updated_at=obj.get('LastModified', datetime.now(timezone.utc)))
            else:
                shards_dir = get_cocli_base_dir() / self.shards_prefix
                if shards_dir.exists():
                    for f in shards_dir.glob("*.usv"):
                        if f.name.startswith("_"):
                            continue
                        shard_id = f.stem
                        # Ensure path is relative to base
                        rel_path = f"{self.shards_prefix}{f.name}"
                        manifest.shards[shard_id] = IndexShard(
                            path=rel_path, 
                            updated_at=datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                        )
            return manifest
        except Exception as e:
            logger.error(f"Manifest bootstrap failed: {e}")
            return manifest

    def add_or_update(self, data: WebsiteDomainCsv) -> None:
        """Writes to sharded inbox for eventual compaction."""
        if not data.domain:
            return
        shard_id = self.get_shard_id(str(data.domain))
        s3_key = f"{self.inbox_root}{shard_id}/{slugdotify(str(data.domain))}.usv"
        # Sanitize any legacy RS characters
        usv_line = data.to_usv().replace("\x1e", "")
        self._write_object(s3_key, usv_line)

    def query(self, sql_where: Optional[str] = None, include_shards: bool = True, include_inbox: bool = True, shard_paths: Optional[List[str]] = None) -> List[WebsiteDomainCsv]:
        """
        Queries the unified index using DuckDB.
        Performs a UNION ALL of shards and inbox, then deduplicates by domain.
        """
        import duckdb
        con = duckdb.connect(database=':memory:')
        
        manifest = self.get_latest_manifest()
        
        # S3 Setup for DuckDB
        if self.is_cloud:
            con.execute("INSTALL httpfs;")
            con.execute("LOAD httpfs;")
            
            # Use credentials from campaign if available
            from .config import load_campaign_config
            config = load_campaign_config(self.campaign.name)
            aws_config = config.get("aws", {})
            region = aws_config.get("region_name", "us-east-1")
            con.execute(f"SET s3_region='{region}';")
            
            # Pass through current credentials
            session = boto3.Session()
            creds = session.get_credentials()
            if creds:
                frozen = creds.get_frozen_credentials()
                con.execute(f"SET s3_access_key_id='{frozen.access_key}';")
                con.execute(f"SET s3_secret_access_key='{frozen.secret_key}';")
                if frozen.token:
                    con.execute(f"SET s3_session_token='{frozen.token}';")

        field_names = list(WebsiteDomainCsv.model_fields.keys())
        # Wrap each field in trim and replace CHR(30) (\x1e) to remove any hidden separators
        trim_cols = ", ".join([f"trim(replace({col}, CHR(30), '')) as {col}" for col in field_names])
        columns = {k: 'VARCHAR' for k in field_names}
        sub_queries = []

        # 1. Manifest Shards
        if include_shards or shard_paths:
            if not shard_paths and manifest.shards:
                shard_paths = sorted(list(set([self._get_path(s.path) for s in manifest.shards.values()] )))
            
            if shard_paths:
                path_list = "', '".join(shard_paths)
                sub_queries.append(f"""
                    SELECT {trim_cols} FROM read_csv(['{path_list}'], 
                        delim='\x1f',
                        header=False, 
                        columns={columns}, 
                        auto_detect=False, 
                        all_varchar=True,
                        null_padding=True,
                        strict_mode=False
                    )
                """)

        # 2. Inbox (Directly list files to avoid glob issues on S3)
        if include_inbox:
            inbox_paths = []
            try:
                if self.is_cloud:
                    paginator = self.s3_client.get_paginator('list_objects_v2')
                    pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.inbox_root)
                    for page in pages:
                        for obj in page.get('Contents', []):
                            key = obj['Key']
                            if key.endswith(".usv") and not key.split('/')[-1].startswith("_"):
                                inbox_paths.append(self._get_path(key))
                else:
                    inbox_dir = self.root_dir / self.inbox_root
                    if inbox_dir.exists():
                        inbox_paths = [str(f) for f in inbox_dir.rglob("*.usv") if not f.name.startswith("_")]
            except Exception:
                pass

            if inbox_paths:
                path_list = "', '".join(inbox_paths)
                sub_queries.append(f"""
                    SELECT {trim_cols} FROM read_csv(['{path_list}'], 
                        delim='\x1f',
                        header=False, 
                        columns={columns}, 
                        auto_detect=False, 
                        all_varchar=True,
                        null_padding=True,
                        strict_mode=False
                    )
                """)

        try:
            base_query = " UNION ALL ".join(sub_queries)
            full_query = f"""
                SELECT * FROM (
                    SELECT *, row_number() OVER (PARTITION BY domain ORDER BY updated_at DESC) as rn
                    FROM ({base_query})
                ) WHERE rn = 1
            """
            # Use 'contains' for simple tag matching since tags are stored as 'tag1;tag2' in USV
            if sql_where:
                # Hotfix for list_contains vs string contains
                sql_where = sql_where.replace("list_contains(tags,", "contains(tags,")
                full_query = f"SELECT * FROM ({full_query}) WHERE {sql_where}"
            
            logger.debug(f"Unified Index Query: {full_query}")
            results = con.execute(full_query).fetchall()
            items = []
            seen = set()
            for row in results:
                data = dict(zip(field_names, row))
                if data['domain'] in seen:
                    continue
                if data.get('tags'):
                    data['tags'] = data['tags'].split(';')
                else:
                    data['tags'] = []
                items.append(WebsiteDomainCsv.model_validate(data))
                seen.add(data['domain'])
            return items
        except Exception as e:
            logger.error(f"Unified Index Query failed: {e}")
            return []

    def get_by_domain(self, domain: str) -> Optional[WebsiteDomainCsv]:
        # 1. Check Inbox first (fastest, atomic source of truth)
        shard_id = self.get_shard_id(domain)
        s3_key = f"{self.inbox_root}{shard_id}/{slugdotify(domain)}.usv"
        try:
            content = self._read_object(s3_key)
            return WebsiteDomainCsv.from_usv(content)
        except Exception:
            pass
            
        # 2. Check the specific Shard
        manifest = self.get_latest_manifest()
        if shard_id in manifest.shards:
            shard_path = self._get_path(manifest.shards[shard_id].path)
            results = self.query(f"domain = '{domain}'", include_inbox=False, include_shards=False, shard_paths=[shard_path])
            return results[0] if results else None
        
        return None

    def backfill_from_companies(self, campaign_tag: str, limit: int = 0) -> int:
        """
        Populates the domain inbox by scanning company directories for website enrichment.
        Uses a generator to keep memory usage low.
        """
        from pathlib import Path
        from .config import get_companies_dir
        from .text_utils import parse_frontmatter
        from ..utils.yaml_utils import resilient_safe_load
        import re
        import yaml
        import time

        # Setup internal logging for backfill
        logs_dir = Path(".logs")
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / f"backfill_domains_{self.campaign.name}_{int(time.time())}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(file_handler)

        companies_dir = get_companies_dir()
        added_count = 0
        processed_count = 0

        logger.info(f"Starting domain backfill for tag: {campaign_tag}. Detailed log: {log_file}")

        try:
            for company_path in companies_dir.iterdir():
                if not company_path.is_dir():
                    continue
                
                if limit and processed_count >= limit:
                    break

                # 1. Fast Tag Check
                tags_path = company_path / "tags.lst"
                if not tags_path.exists():
                    continue
                
                try:
                    tags = tags_path.read_text().splitlines()
                    if campaign_tag not in [t.strip() for t in tags]:
                        continue
                except Exception:
                    continue

                processed_count += 1

                # 2. Extract Data from website.md
                website_md = company_path / "enrichments" / "website.md"
                if not website_md.exists():
                    continue

                try:
                    content = website_md.read_text()
                    frontmatter_str = parse_frontmatter(content)
                    if not frontmatter_str:
                        continue

                    # Clean problematic YAML tags
                    cleaned_yaml = re.sub(r'!!python/object/new:cocli\.models\.[a-z_]+\.[A-Za-z]+', '', frontmatter_str)
                    cleaned_yaml = re.sub(r'args:\s*\[([^\]]+)\]', r'\1', cleaned_yaml)

                    try:
                        data = yaml.safe_load(cleaned_yaml)
                    except Exception:
                        data = resilient_safe_load(frontmatter_str)

                    if not data:
                        continue

                    domain = data.get("domain") or company_path.name
                    record = WebsiteDomainCsv(
                        domain=domain,
                        company_name=data.get("company_name") or company_path.name,
                        is_email_provider=data.get("is_email_provider", False),
                        updated_at=data.get("updated_at") or datetime.now(timezone.utc),
                        tags=[t.strip() for t in tags]
                    )
                    
                    self.add_or_update(record)
                    added_count += 1

                except Exception as e:
                    logger.error(f"Backfill error processing {company_path.name}: {e}")
        finally:
            logger.removeHandler(file_handler)
            file_handler.close()

        return added_count

    def compact_inbox(self) -> None:
        """
        Merges all items currently in the inbox into their respective deterministic shards (00-ff).
        Updates the manifest to point to the new shard versions.
        """
        logger.info(f"Starting deterministic inbox compaction for {self.campaign.name}...")
        
        # 1. Collect all items from Inbox
        inbox_items = self.query(include_shards=False)
        if not inbox_items:
            logger.info("Inbox is empty, nothing to compact.")
            return

        # 2. Group by shard ID (latest wins)
        shard_groups: Dict[str, Dict[str, WebsiteDomainCsv]] = {}
        for item in inbox_items:
            shard_id = self.get_shard_id(str(item.domain))
            if shard_id not in shard_groups:
                shard_groups[shard_id] = {}
            
            if item.domain not in shard_groups[shard_id] or item.updated_at > shard_groups[shard_id][item.domain].updated_at:
                shard_groups[shard_id][str(item.domain)] = item

        # 3. Update Manifest
        manifest = self.get_latest_manifest()
        import uuid

        # 4. Process each shard
        for shard_id, new_items in shard_groups.items():
            logger.info(f"Processing shard {shard_id} with {len(new_items)} new/updated items...")
            
            # 4a. Load existing items from this shard if it exists
            existing_items: Dict[str, WebsiteDomainCsv] = {}
            if shard_id in manifest.shards:
                try:
                    shard_content = self._read_object(manifest.shards[shard_id].path)
                    for line in shard_content.strip("\n").split("\n"):
                        if not line.strip():
                            continue
                        item = WebsiteDomainCsv.from_usv(line)
                        existing_items[str(item.domain)] = item
                except Exception as e:
                    logger.warning(f"Could not read existing shard {shard_id}: {e}")

            # 4b. Merge
            existing_items.update(new_items)
            
            # 4c. Write new Shard Version
            new_shard_key = f"{self.shards_prefix}{shard_id}.usv"
            # Join items (each has its own trailing newline)
            shard_content = "".join([item.to_usv().replace("\x1e", "") for item in existing_items.values()])
            self._write_object(new_shard_key, shard_content)
            
            # 4d. Update Manifest Entry
            manifest.shards[shard_id] = IndexShard(
                path=new_shard_key,
                record_count=len(existing_items),
                schema_version=6,
                updated_at=datetime.now(timezone.utc)
            )

        # 5. Save Manifest
        manifest_key = f"{self.manifests_prefix}{uuid.uuid4()}.usv"
        self._write_object(manifest_key, manifest.to_usv())
        
        # 6. Swap Pointer
        self._write_object(self.latest_pointer_key, manifest_key)
        
        logger.info(f"Compaction complete. Processed {len(shard_groups)} shards.")
        
        # 7. Cleanup Inbox
        logger.info("Cleaning up processed inbox files...")
        for item in inbox_items:
            shard_id = self.get_shard_id(str(item.domain))
            # Use relative keys for _delete_object
            inbox_key = f"{self.inbox_root}{shard_id}/{slugdotify(str(item.domain))}.usv"
            try:
                self._delete_object(inbox_key)
            except Exception as e:
                logger.error(f"Failed to delete inbox file {inbox_key}: {e}")
