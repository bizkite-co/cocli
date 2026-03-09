import logging
from pathlib import Path
from ..paths import paths
from ..sharding import get_place_id_shard

logger = logging.getLogger(__name__)

class ProspectsStore:
    """
    Managed store for Google Maps Prospects.
    Handles sharding, WAL (Hot), and Checkpoint (Cold) layers.
    Implements the ManagedStore protocol.
    """
    
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        # Use paths authority for the base index directory
        self._root = paths.campaign_prospect_index(campaign_name)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def s3_prefix(self) -> str:
        return f"campaigns/{self.campaign_name}/indexes/google_maps_prospects/"

    def resolve(self, identity: str, layer: str = "wal") -> Path:
        """
        identity: Google Place ID.
        layer: 'wal' (Hot) or 'checkpoint' (Cold).
        """
        if layer == "checkpoint":
            return self.root / "prospects.checkpoint.usv"
            
        shard = get_place_id_shard(identity)
        # Authoritative WAL path from paths.py
        return paths.campaign(self.campaign_name).index("google_maps_prospects").wal / shard / f"{identity}.usv"

    def get_s3_key(self, local_path: Path) -> str:
        try:
            rel_path = local_path.relative_to(self.root)
            return f"{self.s3_prefix}{rel_path}"
        except ValueError:
            # Fallback if path is absolute but belongs to this campaign
            return f"{self.s3_prefix}{local_path.name}"

    async def sync(self, direction: str = "up") -> None:
        """S3 parity sync for the prospect index."""
        pass

    def verify_sentinel(self) -> bool:
        sentinel = self.root / "datapackage.json"
        return sentinel.exists()
