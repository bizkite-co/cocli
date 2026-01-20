from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime

class IndexShard(BaseModel):
    path: str  # S3 key or relative path
    record_count: int = 1
    schema_version: int = 1
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class IndexManifest(BaseModel):
    version: int = 1
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    shards: Dict[str, IndexShard] = {} # domain -> IndexShard

    @classmethod
    def get_header(cls) -> str:
        return "domain\x1fpath\x1frecord_count\x1fschema_version\x1fupdated_at"

    def to_usv(self) -> str:
        """Serializes the manifest to a USV string for storage in S3."""
        lines = []
        for domain, shard in self.shards.items():
            line = f"{domain}\x1f{shard.path}\x1f{shard.record_count}\x1f{shard.schema_version}\x1f{shard.updated_at.isoformat()}"
            lines.append(line)
        return "\x1e".join(lines)

    @classmethod
    def from_usv(cls, content: str) -> "IndexManifest":
        """Parses a USV string into an IndexManifest."""
        shards = {}
        if not content.strip():
            return cls(shards=shards)
            
        lines = content.strip("\x1e\n").split("\x1e")
        for line in lines:
            parts = line.split("\x1f")
            if len(parts) >= 5:
                domain, path, count, ver, updated = parts
                shards[domain] = IndexShard(
                    path=path,
                    record_count=int(count),
                    schema_version=int(ver),
                    updated_at=datetime.fromisoformat(updated)
                )
        return cls(shards=shards)
