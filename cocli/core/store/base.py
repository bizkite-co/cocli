from typing import Protocol, Optional
from pathlib import Path

class ManagedStore(Protocol):
    """
    Formal interface for all sharded data stores (Indexes, Queues, Witness collections).
    Ensures standardized path resolution and S3 synchronization.
    """
    
    @property
    def root(self) -> Path:
        """The base filesystem path for this store."""
        ...

    @property
    def s3_prefix(self) -> str:
        """The authoritative S3 prefix for this store."""
        ...

    def resolve(self, identity: str) -> Path:
        """
        Returns the deterministic filesystem path for a specific object identity.
        Example: Lat/Lon string -> Sharded USV path.
        """
        ...

    def get_s3_key(self, local_path: Path) -> str:
        """Converts a local filesystem path to its authoritative S3 key."""
        ...

    async def sync(self, direction: str = "up") -> None:
        """
        Enforces parity between Local and S3.
        'up': Push local changes to S3.
        'down': Pull remote changes to Local.
        """
        ...

    @property
    def wasi_hash(self) -> Optional[str]:
        """The SHA-256 hash of the authoritative WASI module for this store."""
        ...

    def enforce_integrity(self, current_wasi_hash: str) -> bool:
        """
        Ensures that the current execution context matches the store's sentinel.
        Raises error if current_wasi_hash != sentinel_wasi_hash.
        """
        ...

    def verify_sentinel(self) -> bool:
        """
        Verifies the directory identity via datapackage.json sentinel.
        Prevents writing to mismatched or un-initialized directories.
        """
        ...
