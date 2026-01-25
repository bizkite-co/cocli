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
    def indexes(self) -> Path:
        return self.root / "indexes"

    @property
    def queues(self) -> Path:
        return self.root / "queues"

    def queue(self, campaign_slug: str, queue_name: str) -> Path:
        return self.queues / campaign_slug / queue_name

# Global instance
paths = DataPaths()