from pydantic import BaseModel, Field
from typing import List, Optional
import toml
from pathlib import Path
from cocli.core.utils import slugify

class CampaignImport(BaseModel):
    format: str

class GoogleMaps(BaseModel):
    email: str
    one_password_path: str

class Prospecting(BaseModel):
    locations: List[str]
    tools: List[str]
    queries: List[str]
    zoom_out_button_selector: str = Field("div#zoomOutButton", alias="zoom-out-button-selector")
    panning_distance_miles: int = Field(8, alias="panning-distance-miles")
    initial_zoom_out_level: int = Field(3, alias="initial-zoom-out-level")
    omit_zoom_feature: bool = Field(False, alias="omit-zoom-feature")

class Campaign(BaseModel):
    name: str
    tag: str
    domain: str
    company_slug: str = Field(..., alias='company-slug')
    workflows: List[str]
    import_settings: CampaignImport = Field(..., alias='import')
    google_maps: GoogleMaps
    prospecting: Prospecting
    aws_profile_name: Optional[str] = Field(None, alias="aws-profile-name")

    @classmethod
    def create(cls, name: str, company: str, data_home: Path) -> 'Campaign':
        campaign_slug = slugify(name)
        campaign_dir = data_home / "campaigns" / campaign_slug
        campaign_dir.mkdir(parents=True, exist_ok=True)

        config_template_path = data_home / "campaigns" / "config-template.toml"
        config_path = campaign_dir / "config.toml"

        if not config_template_path.exists():
            raise FileNotFoundError(f"Template file not found at {config_template_path}")

        with open(config_template_path, 'r') as f:
            config_data = toml.load(f)

        config_data['campaign']['name'] = name
        config_data['campaign']['company-slug'] = slugify(company)

        with open(config_path, 'w') as f:
            toml.dump(config_data, f)

        # Create other campaign directories and files
        (campaign_dir / 'data').mkdir(exist_ok=True)
        (campaign_dir / 'initiatives').mkdir(exist_ok=True)
        (campaign_dir / 'README.md').touch()

        flat_config = config_data.pop('campaign')
        flat_config.update(config_data)

        return cls.model_validate(flat_config)
