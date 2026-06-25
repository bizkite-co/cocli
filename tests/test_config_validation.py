"""
Test that config files match the expected Pydantic schemas.

This catches config drift (e.g., stale fields, mismatched types) before deployment.
"""

from pathlib import Path
import tomli
import pytest

from cocli.core.config import ScraperSettings


def test_scraper_settings_schema_validation() -> None:
    """
    Validate that cocli_config.toml [scraper] section matches ScraperSettings schema.

    Fails if:
    - Unknown fields exist (e.g., deprecated google_maps_max_pages)
    - Required fields are missing
    - Field types don't match
    """
    config_file = Path("data/config/cocli_config.toml")

    if not config_file.exists():
        pytest.skip(f"Config file not found at {config_file}")

    with config_file.open("rb") as f:
        config_data = tomli.load(f)

    # Extract scraper section (if it exists)
    scraper_config = config_data.get("scraper", {})

    if not scraper_config:
        pytest.skip("No [scraper] section in config file")

    # This will raise ValidationError if the config doesn't match the schema
    settings = ScraperSettings(**scraper_config)

    # Verify it loaded successfully
    assert settings is not None
    assert isinstance(settings, ScraperSettings)
