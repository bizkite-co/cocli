from pydantic import BaseModel, Field
from typing import List, Optional
import toml
from pathlib import Path
from cocli.core.text_utils import slugify

class CampaignImport(BaseModel):
    format: str

class AwsSettings(BaseModel):
    profile: str
    hosted_zone_id: Optional[str] = Field(None, alias="hosted-zone-id")

class GoogleMaps(BaseModel):
    email: str
    one_password_path: str

class Prospecting(BaseModel):
    locations: List[str]
    keywords: List[str] = Field(default_factory=list)
    target_locations_csv: Optional[str] = Field(None, alias="target-locations-csv")
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
    aws: Optional[AwsSettings] = None

    @classmethod
    def load(cls, name: str, data_home: Optional[Path] = None) -> 'Campaign':
        from cocli.core.config import load_campaign_config
        config_data = load_campaign_config(name)
        if not config_data:
            raise ValueError(f"Campaign config for '{name}' not found or empty.")
        
        # Flatten the config for validation (move [campaign] keys to top level)
        if 'campaign' in config_data:
            flat_config = config_data.pop('campaign')
            flat_config.update(config_data)
        else:
            flat_config = config_data

        return cls.model_validate(flat_config)

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
