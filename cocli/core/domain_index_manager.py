import logging
import os
import boto3
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
            
        # Common Path Components
        self.inbox_prefix = "indexes/domains/"
        self.shards_prefix = "indexes/shards/"
        self.manifests_prefix = "indexes/manifests/"
        self.latest_pointer_key = "indexes/LATEST"

    def _init_s3_client(self, aws_config: Dict[str, Any]) -> None:
        try:
            if os.getenv("COCLI_RUNNING_IN_FARGATE"):
                session = boto3.Session()
            else:
                aws_profile = os.getenv("AWS_PROFILE") or aws_config.get("profile") or aws_config.get("aws_profile")
                session = boto3.Session(profile_name=aws_profile)
            
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
        """Creates an initial manifest by scanning the inbox."""
        manifest = IndexManifest()
        try:
            if self.is_cloud:
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.inbox_prefix)
                for page in pages:
                    for obj in page.get('Contents', []):
                        key = str(obj['Key'])
                        if not key.endswith(".usv") or key.split('/')[-1].startswith("_"):
                            continue
                        domain = key.split('/')[-1].replace(".usv", "")
                        manifest.shards[domain] = IndexShard(path=key, updated_at=obj.get('LastModified', datetime.now(timezone.utc)))
            else:
                inbox_dir = get_cocli_base_dir() / self.inbox_prefix
                if inbox_dir.exists():
                    for f in inbox_dir.glob("*.usv"):
                        if f.name.startswith("_"):
                            continue
                        domain = f.stem
                        manifest.shards[domain] = IndexShard(path=f"{self.inbox_prefix}{f.name}", updated_at=datetime.fromtimestamp(f.stat().st_mtime))
            return manifest
        except Exception as e:
            logger.error(f"Manifest bootstrap failed: {e}")
            return manifest

    def add_or_update(self, data: WebsiteDomainCsv) -> None:
        """Writes to inbox for eventual compaction."""
        if not data.domain:
            return
        s3_key = f"{self.inbox_prefix}{slugdotify(str(data.domain))}.usv"
        self._write_object(s3_key, data.to_usv())

    def query(self, sql_where: Optional[str] = None, include_shards: bool = True, include_inbox: bool = True) -> List[WebsiteDomainCsv]:
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
        columns = {k: 'VARCHAR' for k in field_names}
        sub_queries = []

        # 1. Manifest Shards
        if include_shards and manifest.shards:
            paths = sorted(list(set([self._get_path(s.path) for s in manifest.shards.values()] )))
            path_list = "', '".join(paths)
            sub_queries.append(f"""
                SELECT * FROM read_csv(['{path_list}'], 
                    delim=CHR(31), 
                    header=False, 
                    quote='', 
                    escape='', 
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
                    pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.inbox_prefix)
                    for page in pages:
                        for obj in page.get('Contents', []):
                            key = obj['Key']
                            if key.endswith(".usv") and not key.split('/')[-1].startswith("_"):
                                inbox_paths.append(self._get_path(key))
                else:
                    inbox_dir = get_cocli_base_dir() / self.inbox_prefix
                    if inbox_dir.exists():
                        inbox_paths = [str(f) for f in inbox_dir.glob("*.usv") if not f.name.startswith("_")]
            except Exception:
                pass

            if inbox_paths:
                path_list = "', '".join(inbox_paths)
                sub_queries.append(f"""
                    SELECT * FROM read_csv(['{path_list}'], 
                        delim=CHR(31), 
                        header=False, 
                        quote='', 
                        escape='', 
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
        results = self.query(f"domain = '{domain}'")
        return results[0] if results else None

    def compact_inbox(self) -> None:
        """
        Merges all items currently in the inbox into a single new shard.
        Updates the manifest to point these domains to the new shard.
        """
        logger.info(f"Starting inbox compaction for {self.campaign.name}...")
        
        # 1. Collect all items from Inbox
        inbox_items = self.query(include_shards=False)
        if not inbox_items:
            logger.info("Inbox is empty, nothing to compact.")
            return

        # 2. Group by domain (latest wins)
        latest_items: Dict[str, WebsiteDomainCsv] = {}
        for item in inbox_items:
            if item.domain not in latest_items or item.updated_at > latest_items[item.domain].updated_at:
                latest_items[item.domain] = item

        # 3. Write new Shard
        import uuid
        shard_id = str(uuid.uuid4())
        shard_key = f"{self.shards_prefix}{shard_id}.usv"
        
        shard_content = "\n".join([item.to_usv() for item in latest_items.values()]) + "\n"
        self._write_object(shard_key, shard_content)
        
        # 4. Update Manifest
        manifest = self.get_latest_manifest()
        new_shard_ptr = IndexShard(
            path=shard_key,
            schema_version=6,
            updated_at=datetime.now(timezone.utc)
        )
        
        for domain in latest_items.keys():
            manifest.shards[domain] = new_shard_ptr
            
        # 5. Save Manifest
        manifest_key = f"{self.manifests_prefix}{uuid.uuid4()}.usv"
        self._write_object(manifest_key, manifest.to_usv())
        
        # 6. Swap Pointer
        self._write_object(self.latest_pointer_key, manifest_key)
        
        logger.info(f"Compacted {len(latest_items)} domains into {shard_key}")
        
        # 7. (Optional) Cleanup Inbox - We'll leave this for now to be safe, 
        # or implement a 'cleanup' that deletes files older than the manifest update.
