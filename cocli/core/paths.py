from pathlib import Path
from pydantic import BaseModel
import os
import platform
import logging

logger = logging.getLogger(__name__)

class ValidatedPath(BaseModel):
    path: Path

    def exists(self) -> bool:
        return self.path.exists()

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        self.path.mkdir(parents=parents, exist_ok=exist_ok)

    def __truediv__(self, other):
        return self.path / other

    def __str__(self):
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

def get_cocli_data_home() -> Path:
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
        
    return (base / "cocli_data").resolve()

class DataPaths:
    """
    Central Authority for Data Directory Paths.
    """
    def __init__(self, root: Path = None):
        self.root = root or get_cocli_data_home()

    @property
    def campaigns(self) -> Path:
        return self.root / "campaigns"

    def campaign(self, campaign_slug: str) -> Path:
        return self.campaigns / campaign_slug

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

# Global instance
paths = DataPaths()