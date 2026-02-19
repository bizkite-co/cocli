from pathlib import Path
import os
import platform
import logging
from typing import Optional, Iterator
from .ordinant import IndexName, QueueName, StateFolder
from pydantic import BaseModel

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
        return ValidatedPath(path=path.absolute())

class PathObject:
    """Base class for hierarchical path objects with .ensure() support."""
    def __init__(self, path: Path):
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def ensure(self) -> Path:
        """Creates the directory if it doesn't exist and returns the Path."""
        self._path.mkdir(parents=True, exist_ok=True)
        return self._path

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        """Compatibility method for raw Path.mkdir."""
        self._path.mkdir(parents=parents, exist_ok=exist_ok)

    def __str__(self) -> str:
        return str(self._path)

    def __truediv__(self, other: str) -> Path:
        return self._path / other

    def exists(self) -> bool:
        return self._path.exists()

    def is_dir(self) -> bool:
        return self._path.is_dir()

class QueuePaths(PathObject):
    def state(self, folder: StateFolder) -> Path:
        return self._path / folder
    
    @property
    def pending(self) -> Path: return self.state("pending")
    @property
    def completed(self) -> Path: return self.state("completed")
    @property
    def sideline(self) -> Path: return self.state("sideline")

class IndexPaths(PathObject):
    @property
    def wal(self) -> Path:
        return self._path / "wal"
    
    @property
    def checkpoint(self) -> Path:
        # Standard checkpoint name across all indexes
        if self._path.name == "google_maps_prospects":
            return self._path / "prospects.checkpoint.usv"
        return self._path / f"{self._path.name}.checkpoint.usv"

class CampaignPaths(PathObject):
    @property
    def indexes(self) -> Path:
        return self._path / "indexes"
    
    def index(self, name: IndexName) -> IndexPaths:
        return IndexPaths(self.indexes / name)

    @property
    def queues(self) -> Path:
        return self._path / "queues"
    
    def queue(self, name: QueueName) -> QueuePaths:
        return QueuePaths(self.queues / name)

    @property
    def exports(self) -> Path:
        return self._path / "exports"

    @property
    def config(self) -> Path:
        return self._path / "config.toml"

    @property
    def config_file(self) -> Path:
        # Legacy alias
        return self.config

class EntryPaths(PathObject):
    @property
    def index(self) -> Path:
        return self._path / "_index.md"

    @property
    def tags(self) -> Path:
        return self._path / "tags.lst"

    @property
    def enrichments(self) -> Path:
        return self._path / "enrichments"
    
    def enrichment(self, name: str) -> Path:
        if not name.endswith(".md") and not name.endswith(".html"):
            name = f"{name}.md"
        return self.enrichments / name

    def meeting(self, filename: str) -> Path:
        if not filename.endswith(".md"):
            filename = f"{filename}.md"
        return self._path / "meetings" / filename

class CollectionPaths(PathObject):
    def entry(self, slug_or_path: str | Path) -> EntryPaths:
        if isinstance(slug_or_path, Path):
            return EntryPaths(slug_or_path)
        return EntryPaths(self._path / slug_or_path)

class WalPaths(PathObject):
    @property
    def root(self) -> Path:
        return self._path

    def journal(self, node_id: str, date_str: Optional[str] = None) -> Path:
        if not date_str:
            from datetime import datetime, UTC
            date_str = datetime.now(UTC).strftime("%Y%m%d")
        return self._path / f"{date_str}_{node_id}.usv"

    def glob(self, pattern: str) -> Iterator[Path]:
        return self._path.glob(pattern)

def get_data_home() -> Path:
    """Determines the root data directory."""
    if "COCLI_DATA_HOME" in os.environ:
        return Path(os.environ["COCLI_DATA_HOME"]).expanduser().resolve()
    
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
        
    return (base / "data").resolve()

class DataPaths:
    """
    Central Authority for Data Directory Paths (OMAP Implementation).
    Uses dot-notation hierarchy: paths.campaign(slug).index(name).ensure()
    """
    def __init__(self, root: Optional[Path] = None):
        self.root = root or get_data_home()

    @property
    def campaigns(self) -> Path:
        return self.root / "campaigns"

    def campaign(self, slug: str) -> CampaignPaths:
        return CampaignPaths(self.root / "campaigns" / slug)

    @property
    def companies(self) -> CollectionPaths:
        return CollectionPaths(self.root / "companies")

    @property
    def people(self) -> CollectionPaths:
        return CollectionPaths(self.root / "people")

    @property
    def wal(self) -> WalPaths:
        return WalPaths(self.root / "wal")

    @property
    def indexes(self) -> Path:
        return self.root / "indexes"

    # --- Legacy Delegation Methods (for backward compatibility) ---
    def queue(self, campaign_slug: str, queue_name: QueueName) -> Path:
        return self.campaign(campaign_slug).queue(queue_name).path

    def campaign_indexes(self, campaign_slug: str) -> Path:
        return self.campaign(campaign_slug).indexes

    def campaign_exports(self, campaign_slug: str) -> Path:
        return self.campaign(campaign_slug).exports

    def campaign_exclusions(self, campaign_slug: str) -> Path:
        return self.campaign(campaign_slug).indexes / "exclude"

    def campaign_prospect_index(self, campaign_slug: str) -> Path:
        return self.campaign(campaign_slug).index("google_maps_prospects").path

    def wal_journal(self, node_id: str, date_str: Optional[str] = None) -> Path:
        return self.wal.journal(node_id, date_str)

    def wal_remote_journal(self, node_id: str) -> Path:
        return self.wal.path / f"remote_{node_id}.usv"

    def wal_target_id(self, entity_path: Path) -> str:
        try:
            return str(entity_path.relative_to(self.root))
        except ValueError:
            return f"{entity_path.parent.name}/{entity_path.name}"

    # --- S3 Namespace (Mirrors hierarchy) ---
    def s3_campaign(self, slug: str) -> str:
        return f"campaigns/{slug}/"

    def s3_campaign_root(self, slug: str) -> str:
        return self.s3_campaign(slug)

    def s3_index(self, campaign_slug: str, name: IndexName) -> str:
        return f"{self.s3_campaign(campaign_slug)}indexes/{name}/"

    def s3_queue(self, campaign_slug: str, name: QueueName) -> str:
        return f"{self.s3_campaign(campaign_slug)}queues/{name}/"

    def s3_queue_pending(self, campaign_slug: str, queue_name: QueueName, shard: str = "", task_id: str = "") -> str:
        base = f"{self.s3_queue(campaign_slug, queue_name)}pending/"
        if shard:
            base += f"{shard}/"
            if task_id:
                base += f"{task_id}/"
        return base

    def s3_company(self, slug: str) -> str:
        return f"companies/{slug}/"

    def s3_company_index(self, slug: str) -> str:
        return f"{self.s3_company(slug)}_index.md"

    def s3_website_enrichment(self, slug: str) -> str:
        return f"{self.s3_company(slug)}enrichments/website.md"

    def s3_status_root(self) -> str:
        return "status/"

    def s3_heartbeat(self, hostname: str) -> str:
        return f"{self.s3_status_root()}{hostname}.json"

# Global instance
paths = DataPaths()
