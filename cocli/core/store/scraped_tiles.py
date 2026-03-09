import logging
from pathlib import Path
from typing import Optional
from .models import TilePath
from ..paths import paths

logger = logging.getLogger(__name__)

class ScrapedTilesStore:
    """
    Managed store for high-speed witness files (scraped-tiles).
    Implements the ManagedStore protocol.
    """
    
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name
        # Note: Scraped tiles are currently global in paths.root / "indexes" / "scraped-tiles"
        # but can also be campaign specific.
        self._root = paths.root / "indexes" / "scraped-tiles"

    @property
    def root(self) -> Path:
        return self._root

    @property
    def s3_prefix(self) -> str:
        return "indexes/scraped-tiles/"

    def resolve(self, identity: str) -> Path:
        """
        identity: 'latitude_longitude_phrase'
        """
        parts = identity.split("_", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid identity for ScrapedTilesStore: {identity}")
        
        return TilePath(
            root=self.root,
            latitude=float(parts[0]),
            longitude=float(parts[1]),
            phrase=parts[2]
        ).to_path()

    def get_s3_key(self, local_path: Path) -> str:
        try:
            rel_path = local_path.relative_to(self.root)
            return f"{self.s3_prefix}{rel_path}"
        except ValueError:
            raise ValueError(f"Path {local_path} is not under store root {self.root}")

    async def sync(self, direction: str = "up") -> None:
        """Rapid sync via rsync for local cluster or aws s3 sync for cloud."""
        # This would integrate with existing sync logic
        # For now, placeholder for the protocol
        pass

    @property
    def wasi_hash(self) -> Optional[str]:
        """Loads wasi_hash from datapackage.json."""
        import json
        sentinel_path = self.root / "datapackage.json"
        if not sentinel_path.exists():
            return None
        try:
            with open(sentinel_path, "r") as f:
                data = json.load(f)
                val = data.get("cocli:wasi_hash")
                return str(val) if val is not None else None
        except Exception:
            return None

    def enforce_integrity(self, current_wasi_hash: str) -> bool:
        sentinel_hash = self.wasi_hash
        if sentinel_hash and current_wasi_hash != sentinel_hash:
            raise RuntimeError(
                f"WASI Integrity Violation for {self.root}\n"
                f"Expected Hash: {sentinel_hash}\n"
                f"Current Hash:  {current_wasi_hash}\n"
                "Data position shifts prevented. Please perform a formal migration."
            )
        return True

    def verify_sentinel(self) -> bool:
        """
        Verifies the directory identity via datapackage.json sentinel.
        """
        import json
        from ..ordinant import IndexIdentity
        sentinel_path = self.root / "datapackage.json"
        if not sentinel_path.exists():
            return False
            
        try:
            with open(sentinel_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("name") == IndexIdentity.SCRAPED_TILES)
        except Exception:
            return False
