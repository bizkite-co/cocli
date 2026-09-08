from __future__ import annotations

import toml
from pathlib import Path
from cocli.models.campaigns.campaign import Campaign, IcpSettings


def test_icp_settings_defaults() -> None:
    settings = IcpSettings()
    assert settings.min_quality_score == 0.0
    assert settings.require_email is False
    assert settings.require_phone is False
    assert settings.require_domain is False
    assert settings.weights.google_maps_rating == 1.0
    assert settings.weights.reviews_count == 0.5


def test_campaign_load_with_icp_config(tmp_path: Path) -> None:
    config_dict = {
        "campaign": {
            "name": "test-campaign",
            "tag": "test",
            "domain": "test.com",
            "company-slug": "test-slug",
            "workflows": ["outreach"],
        },
        "import": {"format": "csv"},
        "google_maps": {
            "email": "test@example.com",
            "one_password_path": "op://test/path",
        },
        "prospecting": {
            "target-locations": ["Dallas, TX"],
            "queries": ["financial planner"],
            "icp": {
                "min-quality-score": 4.5,
                "require-email": True,
                "require-phone": True,
                "require-domain": False,
                "weights": {
                    "google-maps-rating": 1.5,
                    "reviews-count": 0.8,
                    "search-phrase-relevance": 1.5,
                },
            },
        },
    }

    config_file = tmp_path / "config.toml"
    config_file.write_text(toml.dumps(config_dict), encoding="utf-8")

    campaign_dir = tmp_path / "test-campaign"
    campaign_dir.mkdir()
    (campaign_dir / "config.toml").write_text(toml.dumps(config_dict), encoding="utf-8")

    flat_data = config_dict["campaign"].copy()
    flat_data.update({
        "prospecting": config_dict["prospecting"],
        "import": config_dict["import"],
        "google_maps": config_dict["google_maps"],
    })

    campaign = Campaign.model_validate(flat_data)
    assert campaign.prospecting is not None
    assert campaign.prospecting.icp.min_quality_score == 4.5
    assert campaign.prospecting.icp.require_email is True
    assert campaign.prospecting.icp.require_phone is True
    assert campaign.prospecting.icp.require_domain is False
    assert campaign.prospecting.icp.weights.google_maps_rating == 1.5
    assert campaign.prospecting.icp.weights.reviews_count == 0.8
    assert campaign.prospecting.icp.weights.search_phrase_relevance == 1.5
