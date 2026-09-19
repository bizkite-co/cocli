from __future__ import annotations

from pydantic import ValidationError

from cocli.models.campaigns.campaign import Campaign
from cocli.tui.widgets.application_view import _format_campaign_load_error


def test_campaign_model_allows_missing_import_section() -> None:
    """TUI Campaign.load used to raise 'Field required' with no field name
    when a new campaign had no vestigial [import] block (image-annex, 2026-09-19)."""
    campaign = Campaign.model_validate(
        {
            "name": "image-annex",
            "tag": "image-annex",
            "domain": "image-annex.store",
            "company-slug": "image-annex",
            "workflows": ["prospecting"],
            "google_maps": {
                "email": "a@b.com",
                "one_password_path": "op://x/y",
            },
            "prospecting": {
                "target-locations": ["Fullerton, CA"],
                "queries": ["photographer"],
                "tools": ["google-maps"],
            },
        }
    )
    assert campaign.import_settings.format == "csv"


def test_format_campaign_load_error_names_the_missing_field() -> None:
    try:
        Campaign.model_validate({"name": "x"})
    except ValidationError as exc:
        text = _format_campaign_load_error(exc)
    else:
        raise AssertionError("expected ValidationError")
    assert "tag:" in text
    assert "Field required" in text
    assert "input_value" not in text
