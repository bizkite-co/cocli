# POLICY: frictionless-data-policy-enforcement
from pathlib import Path
from typing import Optional, List
from pydantic import Field

from ..base import BaseUsvModel

class CompanyCacheItem(BaseUsvModel):
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

    @classmethod
    def save_datapackage(cls, path: Path, resource_name: str = "company_search_cache", resource_path: str = "company_cache.usv") -> None:
        """Saves the datapackage.json to the specified directory."""
        super().save_datapackage(path, resource_name, resource_path)
