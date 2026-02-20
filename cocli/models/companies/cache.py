import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ...core.utils import UNIT_SEP

class CompanyCacheItem(BaseModel):
    """
    A lean representation of human-edited company data for the Quick Search view.
    Replaces the legacy fz_cache JSON.
    """
    slug: str = Field(..., description="Filesystem slug")
    name: str = Field(..., description="Business name from Markdown")
    type: str = Field("company", description="Entity type (company/person)")
    domain: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    display: str = Field(..., description="Pre-formatted fzf display string")

    def to_usv(self) -> str:
        """Serializes to a single USV line."""
        cols = [
            self.slug,
            self.name,
            self.type,
            self.domain or "",
            self.email or "",
            self.phone_number or "",
            ";".join(self.tags),
            self.display
        ]
        return UNIT_SEP.join(cols) + "\n"

    @classmethod
    def get_datapackage(cls) -> Dict[str, Any]:
        """Returns the Frictionless Data Package schema."""
        return {
            "profile": "tabular-data-package",
            "name": "company_search_cache",
            "resources": [
                {
                    "name": "cache",
                    "path": "company_cache.usv",
                    "format": "usv",
                    "dialect": {"delimiter": UNIT_SEP, "header": False},
                    "schema": {
                        "fields": [
                            {"name": "slug", "type": "string"},
                            {"name": "name", "type": "string"},
                            {"name": "type", "type": "string"},
                            {"name": "domain", "type": "string"},
                            {"name": "email", "type": "string"},
                            {"name": "phone_number", "type": "string"},
                            {"name": "tags", "type": "string", "description": "Semicolon separated list"},
                            {"name": "display", "type": "string"}
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
