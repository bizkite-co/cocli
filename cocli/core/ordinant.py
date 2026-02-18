from typing import Protocol, Literal, runtime_checkable, Union
from pathlib import Path
import hashlib

# --- The Known Universe (Literals) ---

# Top-level global collections
CollectionName = Literal["companies", "people", "wal"]

# Campaign-specific sharded indexes
IndexName = Union[Literal["google_maps_prospects", "target-tiles", "domains", "emails"], str]

# Campaign-specific task queues
QueueName = Union[Literal["enrichment", "gm-details", "gm-list"], str]

# Standardized folder names for Queues/WAL
StateFolder = Literal["pending", "completed", "sideline", "inbox", "processing"]

# --- Deterministic Sharding ---

def get_shard(identifier: str, strategy: Literal["place_id", "domain", "geo", "none"] = "place_id") -> str:
    """
    Standardized sharding logic for all Ordinant models.
    """
    if not identifier:
        return "_"
    
    if strategy == "place_id":
        # Uses the 6th character (index 5) for 1-level sharding.
        if len(identifier) < 6:
            return identifier[-1] if identifier else "_"
        char = identifier[5]
        return char if char.isalnum() else "_"
        
    elif strategy == "domain":
        # Returns a 2-character hex shard (00-ff)
        return hashlib.sha256(identifier.lower().encode()).hexdigest()[:2]
        
    elif strategy == "geo":
        # Returns the first character of the latitude (e.g., '3', '4', '-')
        return identifier.strip()[0] if identifier.strip() else "_"
        
    return "" # No sharding

@runtime_checkable
class Ordinant(Protocol):
    """
    The Ordinant protocol defines a model that knows its own place 
    within the Data Ordinance. Every persistent model should implement this.
    """
    
    def get_local_path(self) -> Path:
        """Returns the full absolute path to the local file/directory."""
        ...

    def get_remote_key(self) -> str:
        """Returns the relative S3 key (path from bucket root)."""
        ...

    def get_shard_id(self) -> str:
        """Returns the deterministic shard ID (e.g., 'a1' or 'f')."""
        ...

    @property
    def collection(self) -> CollectionName | IndexName | QueueName:
        """Returns the formal name of the collection this item belongs to."""
        ...
