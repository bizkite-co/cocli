from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Optional, Dict, Any
from pathlib import Path

class RawWitness(BaseModel):
    """
    Immutable record of a raw data capture (The 'Witness').
    Stored in data/campaigns/{campaign}/raw/{process}/{shard}/{id}/
    """
    place_id: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_by: str
    campaign_name: str
    url: str
    html: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: str = "1.1.0"

    def get_dir_path(self) -> str:
        from ...core.sharding import get_place_id_shard
        shard = get_place_id_shard(self.place_id)
        return f"raw/gm-details/{shard}/{self.place_id}"

    def save(self, s3_client: Any = None, bucket_name: Optional[str] = None) -> Path:
        """Saves the witness to disk and S3 as a directory of files."""
        from ...core.paths import paths
        
        rel_dir = self.get_dir_path()
        local_dir = paths.campaign(self.campaign_name).path / rel_dir
        local_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Save HTML
        html_path = local_dir / "witness.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.html)
            
        # 2. Save Metadata (exclude HTML from JSON)
        metadata_path = local_dir / "metadata.json"
        meta_json = self.model_dump(exclude={"html"})
        # Convert datetime to string for JSON serialization
        meta_json["captured_at"] = self.captured_at.isoformat()
        
        import json
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(meta_json, indent=2))
            
        if s3_client and bucket_name:
            # Sync the directory to S3
            s3_prefix = f"campaigns/{self.campaign_name}/{rel_dir}"
            s3_client.upload_file(str(html_path), bucket_name, f"{s3_prefix}/witness.html")
            s3_client.upload_file(str(metadata_path), bucket_name, f"{s3_prefix}/metadata.json")
            
        return local_dir

class RawWebsiteWitness(BaseModel):
    """
    Witness for a website enrichment capture.
    Stored in data/campaigns/{campaign}/raw/enrichment/{shard}/{domain}/
    """
    domain: str
    company_slug: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_by: str
    campaign_name: str
    url: str
    html: str
    # Playwright config, headers, etc.
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"

    def get_dir_path(self) -> str:
        from ...core.sharding import get_domain_shard
        shard = get_domain_shard(self.domain)
        # Using domain as ID
        safe_domain = self.domain.replace("/", "_")
        return f"raw/enrichment/{shard}/{safe_domain}"

    def save(self, s3_client: Any = None, bucket_name: Optional[str] = None) -> Path:
        """Saves the witness to disk and S3."""
        from ...core.paths import paths
        
        rel_dir = self.get_dir_path()
        campaign_name = self.campaign_name or "default"
        local_dir = paths.campaign(campaign_name).path / rel_dir
        local_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Save HTML
        html_path = local_dir / "witness.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.html)
            
        # 2. Save Metadata
        metadata_path = local_dir / "metadata.json"
        meta_json = self.model_dump(exclude={"html"})
        meta_json["captured_at"] = self.captured_at.isoformat()
        
        import json
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(meta_json, indent=2))
            
        if s3_client and bucket_name:
            s3_prefix = f"campaigns/{campaign_name}/{rel_dir}"
            s3_client.upload_file(str(html_path), bucket_name, f"{s3_prefix}/witness.html")
            s3_client.upload_file(str(metadata_path), bucket_name, f"{s3_prefix}/metadata.json")
            
        return local_dir
