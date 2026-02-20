import json
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from ..core.utils import UNIT_SEP

class LifecycleItem(BaseModel):
    """
    Represents the progression of a lead through the automated enrichment pipeline.
    """
    place_id: str = Field(..., description="Google Maps Place ID")
    scraped_at: Optional[str] = Field(None, description="ISO date of list discovery")
    details_at: Optional[str] = Field(None, description="ISO date of detail scraping")
    enriched_at: Optional[str] = Field(None, description="ISO date of website enrichment")

    def to_usv(self) -> str:
        """Serializes to a single USV line."""
        cols = [
            self.place_id,
            self.scraped_at or "",
            self.details_at or "",
            self.enriched_at or ""
        ]
        return UNIT_SEP.join(cols) + "\n"

    @classmethod
    def get_datapackage(cls) -> Dict[str, Any]:
        """Returns the Frictionless Data Package schema for this model."""
        return {
            "profile": "tabular-data-package",
            "name": "lifecycle_index",
            "resources": [
                {
                    "name": "lifecycle",
                    "path": "lifecycle.usv",
                    "format": "usv",
                    "dialect": {"delimiter": UNIT_SEP, "header": False},
                    "schema": {
                        "fields": [
                            {"name": "place_id", "type": "string"},
                            {"name": "scraped_at", "type": "string"},
                            {"name": "details_at", "type": "string"},
                            {"name": "enriched_at", "type": "string"}
                        ]
                    }
                }
            ]
        }

    @classmethod
    def save_datapackage(cls, path: Path) -> None:
        """Saves the datapackage.json to the specified directory."""
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "datapackage.json", "w") as f:
            json.dump(cls.get_datapackage(), f, indent=2)
