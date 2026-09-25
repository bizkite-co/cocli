"""Initiative manifest specification and parser for campaign initiatives."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field
import yaml

from cocli.core.paths import paths


class InitiativeTargetCriteria(BaseModel):
    """Declarative criteria for identifying target companies for an initiative."""

    tags: list[str] = Field(default_factory=list)
    company_type: Optional[str] = None
    excluded_tags: list[str] = Field(default_factory=list)
    min_activity_rank: Optional[int] = None


class InitiativeOutreachSpec(BaseModel):
    """Declarative outreach specification for follow-up and sequence rendering."""

    format: Literal["email", "call"] = "email"
    follow_up_delay_days: int = 0
    landing_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None


class InitiativeManifest(BaseModel):
    """Root declarative specification for a campaign initiative."""

    name: str
    description: str = ""
    default_template: str
    target_criteria: InitiativeTargetCriteria = Field(default_factory=InitiativeTargetCriteria)
    outreach: InitiativeOutreachSpec = Field(default_factory=InitiativeOutreachSpec)

    @classmethod
    def load(cls, path: Path) -> InitiativeManifest:
        """Load manifest from a YAML file path."""
        if not path.exists():
            raise FileNotFoundError(f"Initiative manifest not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    @classmethod
    def find(cls, campaign_name: str, initiative_name: str) -> Optional[InitiativeManifest]:
        """Locate and load initiative.yaml within campaigns/<campaign>/initiatives/<initiative>/."""
        manifest_path = (
            paths.campaign(campaign_name).path
            / "initiatives"
            / initiative_name
            / "initiative.yaml"
        )
        if not manifest_path.exists():
            return None
        return cls.load(manifest_path)

    def save(self, path: Path) -> None:
        """Write manifest to a YAML file path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.model_dump(exclude_none=True), f, sort_keys=False)
