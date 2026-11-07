from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import toml
from pydantic import BaseModel, Field, model_validator

from cocli.core.text_utils import slugify
from cocli.models.mail import EmailSettings


class CampaignImport(BaseModel):
    model_config = {"extra": "ignore"}
    format: str

class AwsSettings(BaseModel):
    model_config = {"extra": "ignore"}
    profile: Optional[str] = None
    hosted_zone_id: Optional[str] = Field(None, alias="hosted-zone-id")

class AlertSettings(BaseModel):
    model_config = {"extra": "ignore"}
    ntfy_url: Optional[str] = Field(None, alias="ntfy-url")

class GoogleMaps(BaseModel):
    model_config = {"extra": "ignore"}
    email: str = ""
    one_password_path: str = ""


class IcpQualityWeights(BaseModel):
    model_config = {"extra": "ignore", "populate_by_name": True}
    google_maps_rating: float = Field(1.0, alias="google-maps-rating")
    reviews_count: float = Field(0.5, alias="reviews-count")
    search_phrase_relevance: float = Field(1.2, alias="search-phrase-relevance")


class IcpSettings(BaseModel):
    model_config = {"extra": "ignore", "populate_by_name": True}
    min_quality_score: float = Field(0.0, alias="min-quality-score")
    require_email: bool = Field(False, alias="require-email")
    require_phone: bool = Field(False, alias="require-phone")
    require_domain: bool = Field(False, alias="require-domain")
    weights: IcpQualityWeights = Field(default_factory=lambda: IcpQualityWeights())  # type: ignore[call-arg]


class Prospecting(BaseModel):
    model_config = {"extra": "ignore"}
    locations: Optional[list[str]] = Field(default_factory=list, alias="target-locations")
    keywords: list[str] = Field(default_factory=list)
    target_locations_csv: Optional[str] = Field(None, alias="target-locations-csv")
    tools: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    zoom_out_button_selector: str = Field("div#zoomOutButton", alias="zoom-out-button-selector")
    panning_distance_miles: int = Field(8, alias="panning-distance-miles")
    initial_zoom_out_level: int = Field(3, alias="initial-zoom-out-level")
    omit_zoom_feature: bool = Field(False, alias="omit-zoom-feature")
    strict_keyword_filter: bool = Field(False, alias="strict-keyword-filter")
    icp: IcpSettings = Field(default_factory=lambda: IcpSettings())  # type: ignore[call-arg]

    @model_validator(mode='before')
    @classmethod
    def handle_legacy_locations(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # If 'target-locations' is missing but 'locations' is present, use 'locations'
            if 'target-locations' not in data and 'locations' in data:
                data['target-locations'] = data.pop('locations')
            
            # Ensure queries and tools are lists even if missing
            if 'queries' not in data:
                data['queries'] = []
            if 'tools' not in data:
                data['tools'] = []
        return data


class VideoLoudnessSettings(BaseModel):
    model_config = {"extra": "ignore"}
    I: float = -14.0  # noqa: E741
    TP: float = -1.5
    LRA: float = 11.0


class VideoDenoiseSettings(BaseModel):
    model_config = {"extra": "ignore"}
    nr: int = 10


class VideoTranscriptionSettings(BaseModel):
    model_config = {"extra": "ignore"}
    provider: str = "whisper"
    model: str = "gemini-2.0-flash"
    whisper_model: str = "small"


class VideoSettings(BaseModel):
    model_config = {"extra": "ignore"}
    loudness: VideoLoudnessSettings = Field(default_factory=VideoLoudnessSettings)
    denoise: VideoDenoiseSettings = Field(default_factory=VideoDenoiseSettings)
    transcription: VideoTranscriptionSettings = Field(
        default_factory=VideoTranscriptionSettings
    )


class Campaign(BaseModel):
    model_config = {"extra": "ignore", "populate_by_name": True}

    name: str
    tag: str
    domain: str = Field(default="")
    company_slug: str = Field(..., alias='company-slug')
    workflows: list[str] = Field(default_factory=list)
    promotional_sites: list[str] = Field(default_factory=list, alias="promotional-sites")
    # Optional: new campaigns (image-annex) have no Shopify/CSV import
    # stage. Missing [import] used to fail Campaign.load with a bare
    # "Field required" in the TUI (2026-09-19).
    import_settings: CampaignImport = Field(
        default_factory=lambda: CampaignImport(format="csv"),
        alias="import",
    )
    google_maps: GoogleMaps = Field(default_factory=lambda: GoogleMaps())
    prospecting: Prospecting = Field(default_factory=lambda: Prospecting())  # type: ignore[call-arg]
    aws: Optional[AwsSettings] = None
    alerts: Optional[AlertSettings] = None
    email: Optional[EmailSettings] = None
    video: Optional[VideoSettings] = None

    @model_validator(mode='before')
    @classmethod
    def populate_defaults_before(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "promotional-sites" not in data and "promotional_sites" in data:
                data["promotional-sites"] = data["promotional_sites"]
            if data.get("google_maps") is None:
                data.pop("google_maps", None)
            if data.get("prospecting") is None:
                data.pop("prospecting", None)
        return data

    @classmethod
    @lru_cache(maxsize=32)
    def load(cls, name: str, data_home: Optional[Path] = None) -> Campaign:
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
    def create(
        cls,
        name: str,
        company: str,
        data_home: Path,
        domain: Optional[str] = None,
        promotional_sites: Optional[list[str]] = None,
        email: Optional[str] = None,
        workflows: Optional[list[str]] = None,
        enable_video: bool = False,
        enable_prospecting: bool = True,
    ) -> Campaign:
        campaign_slug = slugify(name)
        campaign_dir = data_home / "campaigns" / campaign_slug
        campaign_dir.mkdir(parents=True, exist_ok=True)

        config_template_path = data_home / "campaigns" / "config-template.toml"
        config_path = campaign_dir / "config.toml"

        if not config_template_path.exists():
            raise FileNotFoundError(f"Template file not found at {config_template_path}")

        with open(config_template_path, 'r') as f:
            config_data = toml.load(f)

        camp_dict = config_data.setdefault('campaign', {})
        camp_dict['name'] = name
        camp_dict['company-slug'] = slugify(company)
        camp_dict['tag'] = campaign_slug
        if domain:
            camp_dict['domain'] = domain
        if promotional_sites:
            camp_dict['promotional-sites'] = promotional_sites

        current_workflows = list(camp_dict.get('workflows', []))
        if workflows is not None:
            current_workflows = list(workflows)
        if enable_video and "video" not in current_workflows:
            current_workflows.append("video")
        if not enable_prospecting and "prospecting" in current_workflows:
            current_workflows.remove("prospecting")
        camp_dict['workflows'] = current_workflows

        if enable_video:
            video_dir = campaign_dir / "video"
            for sub in ("raw", "normalized", "packaged", "uploaded", "job_runs"):
                (video_dir / sub).mkdir(parents=True, exist_ok=True)
            video_cfg = config_data.setdefault('video', {})
            video_cfg.setdefault('loudness', {'I': -14, 'TP': -1.5, 'LRA': 11})
            video_cfg.setdefault('denoise', {'nr': 10})
            video_cfg.setdefault(
                'transcription',
                {
                    'provider': 'whisper',
                    'model': 'gemini-2.0-flash',
                    'whisper_model': 'small',
                },
            )

        if email:
            email_cfg = config_data.setdefault('email', {})
            email_cfg['from_address'] = email
            email_cfg['reply_to'] = email
            email_cfg.setdefault('backend', 'm365')

        if not enable_prospecting:
            config_data.pop('prospecting', None)
            config_data.pop('google_maps', None)

        with open(config_path, 'w') as f:
            toml.dump(config_data, f)

        # Create other campaign directories and files
        (campaign_dir / 'data').mkdir(exist_ok=True)
        (campaign_dir / 'initiatives').mkdir(exist_ok=True)
        (campaign_dir / 'README.md').touch()

        flat_config = config_data.pop('campaign')
        flat_config.update(config_data)

        return cls.model_validate(flat_config)
