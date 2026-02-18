from pathlib import Path
from pydantic import BaseModel
import os
import platform
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ValidatedPath(BaseModel):
    path: Path

    def exists(self) -> bool:
        return self.path.exists()

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        self.path.mkdir(parents=parents, exist_ok=exist_ok)

    def __truediv__(self, other: str) -> Path:
        return self.path / other

    def __str__(self) -> str:
        return str(self.path)

def get_validated_dir(path: Path, description: str) -> ValidatedPath:
    try:
        # Resolve symlinks and absolute path immediately
        resolved_path = path.resolve()
        return ValidatedPath(path=resolved_path)
    except Exception:
        # If the path doesn't exist, we can't resolve it fully if it's not created yet.
        # But we want to return a path object that CAN be created.
        # So we just return the absolute path.
        return ValidatedPath(path=path.absolute())

def get_data_home() -> Path:
    """
    Determines the root data directory.
    """
    if "COCLI_DATA_HOME" in os.environ:
        return Path(os.environ["COCLI_DATA_HOME"]).expanduser().resolve()
    
    # Fallback logic mirroring config.py (but simplified for core path logic)
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
        
    return (base / "data").resolve()

class DataPaths:
    """
    Central Authority for Data Directory Paths.
    """
    def __init__(self, root: Optional[Path] = None):
        self.root = root or get_data_home()

    @property
    def campaigns(self) -> Path:
        return self.root / "campaigns"

    def campaign(self, campaign_slug: str) -> Path:
        """
        Returns the path to a specific campaign.
        Supports namespaced campaigns (e.g. 'test/my-campaign') by allowing slashes.
        """
        # Ensure we don't accidentally escape the campaigns root
        # campaign_slug can be 'test/my-campaign' or 'clients/acme/project-x'
        return self.campaigns / campaign_slug

    def campaign_indexes(self, campaign_slug: str) -> Path:
        return self.campaign(campaign_slug) / "indexes"

    def campaign_exports(self, campaign_slug: str) -> Path:
        return self.campaign(campaign_slug) / "exports"

    def campaign_exclusions(self, campaign_slug: str) -> Path:
        return self.campaign_indexes(campaign_slug) / "exclude"

    def campaign_prospect_index(self, campaign_slug: str) -> Path:
        return self.campaign_indexes(campaign_slug) / "google_maps_prospects"

    @property
    def companies(self) -> Path:
        return self.root / "companies"

    def company(self, company_slug: str) -> Path:
        return self.companies / company_slug

    @property
    def people(self) -> Path:
        return self.root / "people"

    @property
    def wal(self) -> Path:
        return self.root / "wal"

    def wal_journal(self, node_id: str, date_str: Optional[str] = None) -> Path:
        """Returns the path to a local WAL journal file."""
        if not date_str:
            from datetime import datetime, UTC
            date_str = datetime.now(UTC).strftime("%Y%m%d")
        return self.wal / f"{date_str}_{node_id}.usv"

    def wal_remote_journal(self, node_id: str) -> Path:
        """Returns the path to a remote WAL journal file (received via gossip)."""
        return self.wal / f"remote_{node_id}.usv"

    def wal_target_id(self, entity_path: Path) -> str:
        """
        Converts a full entity path (e.g. data/companies/apple) 
        into a stable identifier (e.g. 'companies/apple').
        """
        try:
            # Try to make it relative to the root for a clean 'type/slug' string
            return str(entity_path.relative_to(self.root))
        except ValueError:
            # Fallback if the path is outside the root (e.g. in tests)
            return f"{entity_path.parent.name}/{entity_path.name}"

    @property
    def indexes(self) -> Path:
        return self.root / "indexes"

    @property
    def queues(self) -> Path:
        """
        Root directory for campaign queues.
        Note: New campaign-aware structure is <root>/campaigns/<slug>/queues
        This property returns the legacy root for backward compatibility checks.
        """
        return self.root / "queues"

    def queue(self, campaign_slug: str, queue_name: str) -> Path:
        """
        Returns the path to a campaign-specific queue.
        Mirrors S3 structure: campaigns/<campaign>/queues/<queue_name>/
        """
        return self.campaign(campaign_slug) / "queues" / queue_name

    # --- S3 Namespace Methods ---
    def s3_campaign_root(self, campaign_slug: str) -> str:
        return f"campaigns/{campaign_slug}/"

    def s3_campaign_config(self, campaign_slug: str) -> str:
        """Returns the S3 key for the campaign config.toml."""
        return f"{self.s3_campaign_root(campaign_slug)}config.toml"

    def s3_queue_root(self, campaign_slug: str, queue_name: str) -> str:
        return f"{self.s3_campaign_root(campaign_slug)}queues/{queue_name}/"

    def s3_queue_pending(self, campaign_slug: str, queue_name: str, shard: str = "", task_id: str = "") -> str:
        base = f"{self.s3_queue_root(campaign_slug, queue_name)}pending/"
        if shard:
            base += f"{shard}/"
            if task_id:
                base += f"{task_id}/"
        return base

    def s3_queue_completed(self, campaign_slug: str, queue_name: str, task_id: str = "") -> str:
        base = f"{self.s3_queue_root(campaign_slug, queue_name)}completed/"
        if task_id:
            return f"{base}{task_id}.json"
        return base

    def s3_queue_completed_results(self, campaign_slug: str, queue_name: str, shard: str = "", base_id: str = "") -> str:
        base = f"{self.s3_queue_root(campaign_slug, queue_name)}completed/results/"
        if shard:
            base += f"{shard}/"
            if base_id:
                base += f"{base_id}.json"
        return base

    def s3_queue_sideline(self, campaign_slug: str, queue_name: str, category: str = "C_BACKUP", shard: str = "", task_id: str = "") -> str:
        base = f"{self.s3_queue_root(campaign_slug, queue_name)}sideline/{category}/"
        if shard and task_id:
            return f"{base}{shard}/{task_id}/"
        return base

    def s3_index_root(self, campaign_slug: str, index_name: str) -> str:
        return f"{self.s3_campaign_root(campaign_slug)}indexes/{index_name}/"

    def s3_prospect_index_root(self, campaign_slug: str) -> str:
        """Returns the S3 prefix for the prospect index."""
        return self.s3_index_root(campaign_slug, "google_maps_prospects")

    def s3_email_index_root(self, campaign_slug: str) -> str:
        """Returns the S3 prefix for the email index."""
        return self.s3_index_root(campaign_slug, "emails")

    def s3_wal_root(self) -> str:
        """Returns the S3 prefix for the centralized cluster WAL."""
        return "wal/"

    def s3_company_root(self, company_slug: str) -> str:
        """Returns the S3 prefix for a specific company's data (GLOBAL SHARED)."""
        return f"companies/{company_slug}/"

    def s3_company_index(self, company_slug: str) -> str:
        """Returns the S3 key for a company's _index.md (GLOBAL SHARED)."""
        return f"{self.s3_company_root(company_slug)}_index.md"

    def s3_website_enrichment(self, company_slug: str) -> str:
        """Returns the S3 key for a company's website enrichment result (GLOBAL SHARED)."""
        return f"{self.s3_company_root(company_slug)}enrichments/website.md"

    def s3_status_root(self) -> str:
        return "status/"

    def s3_heartbeat(self, hostname: str) -> str:
        return f"{self.s3_status_root()}{hostname}.json"

# Global instance
paths = DataPaths()