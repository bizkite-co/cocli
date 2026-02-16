import logging
import os
import boto3
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from botocore.config import Config

from ..models.campaign import Campaign
from ..models.website_domain_csv import WebsiteDomainCsv
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
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.is_cloud = False
        
        # Resolve storage type
        from .config import load_campaign_config
        config = load_campaign_config(self.campaign.name)
        aws_config = config.get("aws", {})
        self.bucket_name = os.environ.get("COCLI_S3_BUCKET_NAME") or aws_config.get("data_bucket_name")
        
        if self.bucket_name:
            self.is_cloud = True
            self.base_prefix = "" # Root of bucket
            self.protocol = "s3://"
            self._init_s3_client(aws_config)
        else:
            self.is_cloud = False
            self.root_dir = get_cocli_base_dir() / "indexes"
            self.root_dir.mkdir(parents=True, exist_ok=True)
            self.protocol = "" # Local paths are absolute or relative to CWD
            
        # Common Path Components (Nested within domains/)
        self.inbox_root = "indexes/domains/inbox/"
        self.shards_prefix = "indexes/domains/shards/"
        self.manifests_prefix = "indexes/domains/manifests/"
        self.latest_pointer_key = "indexes/domains/LATEST"

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
            return str(get_cocli_base_dir() / key)

    def _read_object(self, key: str) -> str:
        if self.is_cloud:
            resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return resp["Body"].read().decode("utf-8")
        else:
            path = get_cocli_base_dir() / key
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
            path = get_cocli_base_dir() / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _delete_object(self, key: str) -> None:
        if self.is_cloud:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
        else:
            path = get_cocli_base_dir() / key
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
            return (get_cocli_base_dir() / key).exists()

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
                    inbox_dir = get_cocli_base_dir() / self.inbox_root
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
            full_query = f"SELECT * FROM ({base_query})"
            if sql_where:
                full_query += f" WHERE {sql_where}"
            
            full_query += " ORDER BY updated_at DESC"
            
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
            inbox_key = f"{self.inbox_root}{shard_id}/{slugdotify(str(item.domain))}.usv"
            try:
                self._delete_object(inbox_key)
            except Exception as e:
                logger.error(f"Failed to delete inbox file {inbox_key}: {e}")
