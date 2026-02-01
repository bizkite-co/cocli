from pydantic import BaseModel, Field
from typing import Dict
from datetime import datetime, UTC

class IndexShard(BaseModel):
    path: str  # S3 key or relative path
    record_count: int = 1
    schema_version: int = 6
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class IndexManifest(BaseModel):
    version: int = 1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    shards: Dict[str, IndexShard] = {} # shard_id -> IndexShard

    @classmethod
    def get_header(cls) -> str:
        return "shard_id\x1fpath\x1frecord_count\x1fschema_version\x1fupdated_at"

    def to_usv(self) -> str:
        """Serializes the manifest to a unit-separated string."""
        lines = [self.get_header()]
        for shard_id, shard in sorted(self.shards.items()):
            line = f"{shard_id}\x1f{shard.path}\x1f{shard.record_count}\x1f{shard.schema_version}\x1f{shard.updated_at.isoformat()}"
            lines.append(line)
        # Standard newline join, ending with one newline.
        return "\n".join(lines) + "\n"

    @classmethod
    def from_usv(cls, content: str) -> "IndexManifest":
        """Parses a manifest string."""
        shards: Dict[str, IndexShard] = {}
        if not content or not content.strip():
            return cls(shards=shards)
            
        # Standardize line split
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        
        # Skip header if present
        header = cls.get_header()
        if lines and lines[0] == header:
            lines = lines[1:]

        for line in lines:
            # Handle potential legacy \x1e separators by removing them
            line = line.replace("\x1e", "")
            parts = line.split("\x1f")
            if len(parts) >= 5:
                shard_id, path, count, ver, updated = parts
                shards[shard_id.strip()] = IndexShard(
                    path=path,
                    record_count=int(count),
                    schema_version=int(ver),
                    updated_at=datetime.fromisoformat(updated)
                )
        return cls(shards=shards)