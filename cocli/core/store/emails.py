import logging
import hashlib
from pathlib import Path
from .models import ShardIDPath
from ..paths import paths

logger = logging.getLogger(__name__)

class EmailStore:
    """
    Managed store for enriched email data.
    Handles sharded inbox (Hot) and consolidated shards (Cold).
    Implements the ManagedStore protocol.
    """
    
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self._root = paths.campaign(campaign_name).path / "indexes" / "emails"

    @property
    def root(self) -> Path:
        return self._root

    @property
    def s3_prefix(self) -> str:
        return f"campaigns/{self.campaign_name}/indexes/emails/"

    def get_shard_id(self, domain: str) -> str:
        """Deterministic shard (00-ff) based on domain hash."""
        return hashlib.sha256(domain.encode()).hexdigest()[:2]

    def resolve(self, identity: str, layer: str = "inbox") -> Path:
        """
        identity: domain or email address.
        layer: 'inbox' (Hot individual file) or 'shard' (Cold consolidated file).
        """
        if layer == "shard":
            shard_id = self.get_shard_id(identity)
            return self.root / "shards" / f"{shard_id}.usv"
            
        # For inbox, we assume identity is the email address
        if "@" in identity:
            domain = identity.split("@")[-1]
        else:
            domain = identity
            
        shard_id = self.get_shard_id(domain)
        return ShardIDPath(
            root=self.root / "inbox",
            shard_id=shard_id,
            identity=identity.lower().strip()
        ).to_path()

    def get_s3_key(self, local_path: Path) -> str:
        try:
            rel_path = local_path.relative_to(self.root)
            return f"{self.s3_prefix}{rel_path}"
        except ValueError:
            return f"{self.s3_prefix}{local_path.name}"

    async def sync(self, direction: str = "up") -> None:
        """S3 parity sync for the email index."""
        pass

    def verify_sentinel(self) -> bool:
        # Email index might not have a datapackage.json yet, but it should
        sentinel = self.root / "datapackage.json"
        return sentinel.exists()
