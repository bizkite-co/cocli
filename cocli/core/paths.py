# POLICY: frictionless-data-policy-enforcement
from pathlib import Path
import os
import platform
import logging
from typing import Optional, Iterator, Callable
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
        return ValidatedPath(path=path.absolute())
    except Exception:
        return ValidatedPath(path=path.absolute())

class PathObject:
    """Base class for hierarchical path objects with .ensure() support."""
    def __init__(self, path_factory: Callable[[], Path]):
        self._path_factory = path_factory

    @property
    def path(self) -> Path:
        return self._path_factory()

    def ensure(self) -> Path:
        p = self.path
        p.mkdir(parents=True, exist_ok=True)
        return p

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        self.path.mkdir(parents=parents, exist_ok=exist_ok)

    def __str__(self) -> str:
        return str(self.path)

    def __truediv__(self, other: str) -> Path:
        return self.path / other

    def exists(self) -> bool:
        return self.path.exists()

    def is_dir(self) -> bool:
        return self.path.is_dir()

class QueuePaths(PathObject):
    def state(self, folder: StateFolder) -> Path:
        return self.path / folder
    
    @property
    def pending(self) -> Path: return self.state("pending")
    @property
    def completed(self) -> Path: return self.state("completed")
    @property
    def sideline(self) -> Path: return self.state("sideline")

class IndexPaths(PathObject):
    @property
    def wal(self) -> Path:
        return self.path / "wal"
    
    @property
    def checkpoint(self) -> Path:
        if self.path.name == "google_maps_prospects":
            return self.path / "prospects.checkpoint.usv"
        return self.path / f"{self.path.name}.checkpoint.usv"

    @property
    def runs(self) -> Path:
        return self.path / "runs"

    @property
    def datapackage(self) -> Path:
        return self.path / "datapackage.json"

class CampaignPaths(PathObject):
    @property
    def indexes(self) -> Path:
        return self.path / "indexes"
    
    def index(self, name: IndexName) -> IndexPaths:
        return IndexPaths(lambda: self.indexes / name)

    @property
    def queues(self) -> Path:
        return self.path / "queues"
    
    def queue(self, name: QueueName) -> QueuePaths:
        return QueuePaths(lambda: self.queues / name)

    @property
    def exports(self) -> Path:
        return self.path / "exports"

    @property
    def lifecycle(self) -> Path:
        return self.indexes / "lifecycle" / "lifecycle.usv"

    @property
    def config(self) -> Path:
        return self.path / "config.toml"

class EntryPaths(PathObject):
    @property
    def index(self) -> Path:
        return self.path / "_index.md"

    @property
    def tags(self) -> Path:
        return self.path / "tags.lst"

    @property
    def enrichments(self) -> Path:
        return self.path / "enrichments"
    
    def enrichment(self, name: str) -> Path:
        if not name.endswith(".md") and not name.endswith(".html"):
            name = f"{name}.md"
        return self.enrichments / name

    def meeting(self, filename: str) -> Path:
        if not filename.endswith(".md"):
            filename = f"{filename}.md"
        return self.path / "meetings" / filename

class CollectionPaths(PathObject):
    def entry(self, slug_or_path: str | Path) -> EntryPaths:
        if isinstance(slug_or_path, Path):
            return EntryPaths(lambda: slug_or_path)
        return EntryPaths(lambda: self.path / slug_or_path)

class WalPaths(PathObject):
    @property
    def root(self) -> Path:
        return self.path

    def journal(self, node_id: str, date_str: Optional[str] = None) -> Path:
        if not date_str:
            from datetime import datetime, UTC
            date_str = datetime.now(UTC).strftime("%Y%m%d")
        return self.path / f"{date_str}_{node_id}.usv"

    def glob(self, pattern: str) -> Iterator[Path]:
        return self.path.glob(pattern)

def get_data_home() -> Path:
    """Determines the root data directory, respecting COCLI_DATA_HOME."""
    if "COCLI_DATA_HOME" in os.environ:
        return Path(os.environ["COCLI_DATA_HOME"]).expanduser()
    
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
        
    return base / "data"

class S3QueuePaths:
    def __init__(self, c_slug: str, q_name: QueueName):
        self.base = f"campaigns/{c_slug}/queues/{q_name}/"
    def pending(self, shard: str = "", task_id: str = "") -> str:
        res = self.base + "pending/"
        if shard:
            res += f"{shard}/"
            if task_id:
                res += f"{task_id}/"
        return res

class S3CampaignPaths:
    def __init__(self, campaign_slug: str):
        self.slug = campaign_slug
        self.root = f"campaigns/{campaign_slug}/"
    def index(self, name: IndexName) -> str:
        return f"{self.root}indexes/{name}/"
    def queue(self, name: QueueName) -> S3QueuePaths:
        return S3QueuePaths(self.slug, name)

class S3DataPaths:
    def campaign(self, slug: str) -> S3CampaignPaths:
        return S3CampaignPaths(slug)
    def company(self, slug: str) -> str: return f"companies/{slug}/"
    def company_index(self, slug: str) -> str: return f"companies/{slug}/_index.md"
    def website_enrichment(self, slug: str) -> str: return f"companies/{slug}/enrichments/website.md"
    @property
    def status_root(self) -> str: return "status/"
    def heartbeat(self, hostname: str) -> str: return f"{self.status_root}{hostname}.json"

class DataPaths:
    """
    Central Authority for Data Directory Paths (OMAP Implementation).
    Uses lazy factories to ensure paths always reflect current environment.
    """
    def __init__(self) -> None:
        self.s3 = S3DataPaths()
        self._root: Optional[Path] = None

    @property
    def root(self) -> Path:
        return self._root or get_data_home()

    @root.setter
    def root(self, value: Path) -> None:
        self._root = value

    @root.deleter
    def root(self) -> None:
        self._root = None

    @property
    def campaigns(self) -> Path:
        return self.root / "campaigns"

    def campaign(self, slug: str) -> CampaignPaths:
        return CampaignPaths(lambda: self.root / "campaigns" / slug)

    @property
    def companies(self) -> CollectionPaths:
        return CollectionPaths(lambda: self.root / "companies")

    @property
    def people(self) -> CollectionPaths:
        return CollectionPaths(lambda: self.root / "people")

    @property
    def wal(self) -> WalPaths:
        return WalPaths(lambda: self.root / "wal")

    @property
    def indexes(self) -> Path:
        return self.root / "indexes"

    # --- Legacy Delegation Methods ---
    def queue(self, campaign_slug: str, queue_name: QueueName) -> QueuePaths:
        return self.campaign(campaign_slug).queue(queue_name)

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

# Authoritative Global Instance
paths = DataPaths()
