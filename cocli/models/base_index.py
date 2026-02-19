import json
from pathlib import Path
from typing import List, Dict, Optional, ClassVar
from pydantic import BaseModel
from cocli.core.paths import paths
from cocli.core.ordinant import IndexName, get_shard

class BaseIndexModel(BaseModel):
    """
    SINGLE SOURCE OF TRUTH for all cocli indexes.
    Defines the storage location, schema generation, and versioning.
    """
    # Using ClassVar to ensure these are accessible via the class itself
    INDEX_NAME: ClassVar[str] = "base"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    @classmethod
    def get_index_dir(cls, campaign_name: str) -> Path:
        """Returns the absolute path to this index for a specific campaign."""
        return paths.campaign(campaign_name).index(cls.INDEX_NAME).path

    @property
    def collection(self) -> IndexName:
        return self.INDEX_NAME

    def get_shard_id(self) -> str:
        # Most indexes shard by place_id if available
        identifier = getattr(self, "place_id", None) or getattr(self, "slug", "")
        return get_shard(str(identifier), strategy="place_id")

    def get_local_path(self, campaign_name: str) -> Path:
        """Returns the path to the individual record file (sharded)."""
        # Note: Index records are typically sharded USV files.
        # This implementation assumes the record is stored in a campaign index.
        index_path = self.get_index_dir(campaign_name)
        shard_id = self.get_shard_id()
        # Identity is usually place_id or slug
        identity = getattr(self, "place_id", None) or getattr(self, "company_slug", None) or getattr(self, "slug", "unknown")
        return index_path / shard_id / f"{identity}.usv"

    def get_remote_key(self, campaign_name: str) -> str:
        """Returns the S3 key for this index record."""
        shard_id = self.get_shard_id()
        identity = getattr(self, "place_id", None) or getattr(self, "company_slug", None) or getattr(self, "slug", "unknown")
        return f"campaigns/{campaign_name}/indexes/{self.INDEX_NAME}/{shard_id}/{identity}.usv"

    @classmethod
    def get_datapackage_fields(cls) -> List[Dict[str, str]]:
        """Generates Frictionless Data field definitions from the model fields."""
        fields = []
        for name, field in cls.model_fields.items():
            raw_type = field.annotation
            field_type = "string"
            
            type_str = str(raw_type)
            if "int" in type_str:
                field_type = "integer"
            elif "float" in type_str:
                field_type = "number"
            elif "datetime" in type_str:
                field_type = "datetime"
                
            fields.append({
                "name": name,
                "type": field_type,
                "description": field.description or ""
            })
        return fields

    @classmethod
    def write_datapackage(cls, campaign_name: str, output_dir: Optional[Path] = None) -> Path:
        """Writes the datapackage.json for this index."""
        index_dir = output_dir or cls.get_index_dir(campaign_name)
        index_dir.mkdir(parents=True, exist_ok=True)
        output_path = index_dir / "datapackage.json"
        
        schema = {
            "profile": "tabular-data-package",
            "name": cls.INDEX_NAME,
            "model": cls.__name__,
            "version": cls.SCHEMA_VERSION,
            "resources": [
                {
                    "name": cls.INDEX_NAME,
                    "path": "prospects.checkpoint.usv" if cls.INDEX_NAME == "google_maps_prospects" else f"{cls.INDEX_NAME}.checkpoint.usv",
                    "format": "usv",
                    "dialect": {"delimiter": "\u001f", "header": False},
                    "schema": {"fields": cls.get_datapackage_fields()}
                }
            ]
        }
        
        with open(output_path, 'w') as f:
            json.dump(schema, f, indent=2)
        return output_path