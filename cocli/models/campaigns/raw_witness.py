from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Optional, Dict, Any
from pathlib import Path

class RawWitness(BaseModel):
    """
    Immutable record of a raw data capture (The 'Witness').
    Stored in data/campaigns/{campaign}/raw/{process}/{shard}/{id}.json
    """
    place_id: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_by: str
    campaign_name: str
    url: str
    html: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"

    def get_path(self) -> str:
        from ...core.sharding import get_place_id_shard
        shard = get_place_id_shard(self.place_id)
        return f"raw/gm-details/{shard}/{self.place_id}.json"

    def save(self, s3_client: Any = None, bucket_name: Optional[str] = None) -> Path:
        """Saves the witness to disk and S3."""
        from ...core.paths import paths
        
        rel_path = self.get_path()
        local_path = paths.campaign(self.campaign_name).path / rel_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))
            
        if s3_client and bucket_name:
            s3_key = f"campaigns/{self.campaign_name}/{rel_path}"
            s3_client.upload_file(str(local_path), bucket_name, s3_key)
            
        return local_path
