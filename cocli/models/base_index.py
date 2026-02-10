import json
from pathlib import Path
from typing import List, Dict, Optional, ClassVar
from pydantic import BaseModel
from cocli.core.config import get_campaign_dir

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
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            from ..core.config import get_campaigns_dir
            campaign_dir = get_campaigns_dir() / campaign_name
        return campaign_dir / "indexes" / cls.INDEX_NAME

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