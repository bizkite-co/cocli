"""Unit tests for ReportingService campaign visualization / KML export logic."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import toml

from cocli.application.reporting_service import (
    PublishKmlResult,
    ReportingService,
    VizExportResult,
)
from cocli.core.scrape_index import ScrapedArea


def _area(
    phrase: str = "welders",
    lat_min: float = 30.0,
    lat_max: float = 30.1,
    lon_min: float = -90.0,
    lon_max: float = -89.9,
    items_found: int = 3,
    tile_id: str | None = "30.0_-90.0",
) -> ScrapedArea:
    return ScrapedArea(
        phrase=phrase,
        scrape_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        lat_miles=1.0,
        lon_miles=1.0,
        items_found=items_found,
        tile_id=tile_id,
    )


def _campaign_tree(tmp_path: Path, name: str = "test-campaign") -> Path:
    campaign_dir = tmp_path / "campaigns" / name
    campaign_dir.mkdir(parents=True)
    config = {
        "prospecting": {"queries": ["welders", "fabricators"]},
        "aws": {
            "profile": "test-profile",
            "hosted-zone-domain": "example.com",
        },
    }
    (campaign_dir / "config.toml").write_text(toml.dumps(config))
    return campaign_dir


def test_generate_coverage_kml_writes_files(tmp_path: Path) -> None:
    campaign_dir = _campaign_tree(tmp_path)
    service = ReportingService(campaign_name="test-campaign")
    areas = [
        _area("welders", items_found=2),
        _area("fabricators", lat_min=30.2, lat_max=30.3, items_found=5),
    ]

    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ), patch(
        "cocli.core.scrape_index.ScrapeIndex.get_all_areas_for_phrases",
        return_value=areas,
    ):
        result = service.generate_coverage_kml()

    assert isinstance(result, VizExportResult)
    assert result.success is True
    assert result.count == 2
    assert result.export_dir == campaign_dir / "exports"
    assert (campaign_dir / "exports" / "coverage_grid_aggregated.kml").exists()
    # slugified phrase files
    phrase_files = list((campaign_dir / "exports").glob("coverage_*.kml"))
    assert any("welders" in p.name for p in phrase_files)
    assert any("fabricators" in p.name for p in phrase_files)
    agg = (campaign_dir / "exports" / "coverage_grid_aggregated.kml").read_text()
    assert "Placemark" in agg
    assert "kml" in agg


def test_generate_coverage_kml_empty(tmp_path: Path) -> None:
    campaign_dir = _campaign_tree(tmp_path)
    service = ReportingService(campaign_name="test-campaign")
    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ), patch(
        "cocli.core.scrape_index.ScrapeIndex.get_all_areas_for_phrases",
        return_value=[],
    ):
        result = service.generate_coverage_kml()
    assert result.count == 0
    assert "No scraped areas" in result.message


def test_generate_legacy_scrapes_kml(tmp_path: Path) -> None:
    campaign_dir = _campaign_tree(tmp_path)
    service = ReportingService(campaign_name="test-campaign")
    legacy = [_area(tile_id=None)]
    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ), patch(
        "cocli.core.scrape_index.ScrapeIndex.get_all_scraped_areas",
        return_value=legacy,
    ):
        result = service.generate_legacy_scrapes_kml()

    assert result.count == 1
    out = campaign_dir / "exports" / "legacy_scrapes.kml"
    assert out.exists()
    assert "Legacy: welders" in out.read_text()


def test_resolve_publish_config(tmp_path: Path) -> None:
    campaign_dir = _campaign_tree(tmp_path)
    service = ReportingService(campaign_name="test-campaign")
    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ):
        cfg = service.resolve_publish_config()
    assert cfg["profile"] == "test-profile"
    assert cfg["domain"] == "cocli.example.com"
    assert cfg["bucket_name"] == "cocli-web-assets-example-com"
    assert cfg["campaign_name"] == "test-campaign"


def test_resolve_publish_config_missing_profile(tmp_path: Path) -> None:
    campaign_dir = tmp_path / "campaigns" / "bare"
    campaign_dir.mkdir(parents=True)
    (campaign_dir / "config.toml").write_text("")
    service = ReportingService(campaign_name="bare")
    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ):
        with pytest.raises(ValueError, match="AWS profile required"):
            service.resolve_publish_config()


def test_upload_kml_layers(tmp_path: Path) -> None:
    campaign_dir = _campaign_tree(tmp_path, "ship")
    export_dir = campaign_dir / "exports"
    export_dir.mkdir()
    (export_dir / "coverage_grid_aggregated.kml").write_text("<kml/>")
    (export_dir / "target-areas.kml").write_text("<kml/>")
    (campaign_dir / "ship_prospects.kml").write_text("<kml/>")

    mock_s3 = MagicMock()
    mock_session = MagicMock()
    mock_session.client.return_value = mock_s3
    steps: list[str] = []

    service = ReportingService(campaign_name="ship")
    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ), patch("boto3.Session", return_value=mock_session):
        result = service.upload_kml_layers(
            profile="p",
            bucket_name="b",
            domain="cocli.example.com",
            campaign_name="ship",
            log_callback=steps.append,
        )

    assert isinstance(result, PublishKmlResult)
    assert result.success is True
    assert "kml/ship_aggregated.kml" in result.uploaded_keys
    assert "kml/ship_targets.kml" in result.uploaded_keys
    assert "kml/ship_prospects.kml" in result.uploaded_keys
    assert mock_s3.upload_file.call_count == 3
    mock_s3.put_object.assert_called_once()
    put_kwargs = mock_s3.put_object.call_args.kwargs
    assert put_kwargs["Key"] == "kml/layers.json"
    layers = json.loads(put_kwargs["Body"])
    assert any(layer["name"] == "Prospects" for layer in layers)
    assert any("Uploaded" in s for s in steps)
    assert "Published layers.json" in steps


def test_export_value_resources(tmp_path: Path) -> None:
    campaign_dir = _campaign_tree(tmp_path)
    service = ReportingService(campaign_name="test-campaign")

    class FakeProspect:
        is_value_resource = True
        name = "Resource Co"
        first_category = "Park"
        fee_category = "Free"
        full_address = "1 Main St"
        website = "https://example.com"
        gmb_url = None
        rationale = "Nice"
        average_rating = 4.5
        reviews_count = 10

        @classmethod
        def model_validate(cls, row: Any) -> "FakeProspect":
            return cls()

    mock_manager = SimpleNamespace(
        index_dir=tmp_path / "indexes" / "google_maps_prospects",
        checkpoint_path=tmp_path / "indexes" / "google_maps_prospects" / "prospects.usv"
    )
    mock_manager.index_dir.mkdir(parents=True)
    checkpoint = mock_manager.checkpoint_path
    checkpoint.write_text("dummy\n")


    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ), patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager",
        return_value=mock_manager,
    ), patch(
        "cocli.models.campaigns.indexes.google_maps_prospect.GoogleMapsProspect",
        FakeProspect,
    ), patch(
        "cocli.utils.usv_utils.USVDictReader",
        return_value=[{"x": "1"}],
    ):
        result = service.export_value_resources()

    assert result.count == 1
    out = campaign_dir / "exports" / "resources.json"
    assert out in result.files
    data = json.loads(out.read_text())
    assert data[0]["name"] == "Resource Co"
    assert data[0]["category"] == "Park"


def test_export_value_resources_no_index(tmp_path: Path) -> None:
    campaign_dir = _campaign_tree(tmp_path)
    service = ReportingService(campaign_name="test-campaign")
    mock_manager = SimpleNamespace(
        index_dir=tmp_path / "missing" / "google_maps_prospects",
        checkpoint_path=tmp_path / "missing" / "google_maps_prospects" / "prospects.usv"
    )

    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ), patch(
        "cocli.core.prospects_csv_manager.ProspectsIndexManager",
        return_value=mock_manager,
    ):
        result = service.export_value_resources()
    assert result.count == 0
    assert "No index found" in result.message


def test_place_kml_for_turboship_grid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    campaign_dir = _campaign_tree(tmp_path, "turboship")
    exports = campaign_dir / "exports"
    exports.mkdir()
    source = exports / "target-areas.kml"
    source.write_text("<kml>grid</kml>")
    dest_root = tmp_path / "turboship-exports"
    monkeypatch.chdir(tmp_path)

    service = ReportingService(campaign_name="turboship")
    with patch(
        "cocli.application.reporting_service.get_campaign_dir",
        return_value=campaign_dir,
    ):
        result = service.place_kml_for_turboship(
            campaign_name="turboship",
            turboship_kml_exports_path=Path("turboship-exports"),
            kml_filename="coverage.kml",
            kml_type="grid",
        )

    assert result.success is True
    assert (dest_root / "coverage.kml").read_text() == "<kml>grid</kml>"


def test_require_campaign_dir_errors() -> None:
    # Empty constructor falls back to get_campaign(); force empty context.
    with patch(
        "cocli.application.reporting_service.get_campaign", return_value=None
    ):
        service = ReportingService(campaign_name=None)
        assert service.campaign_name == ""
        with pytest.raises(ValueError, match="No campaign name"):
            service._require_campaign_dir()

    service = ReportingService(campaign_name="missing")
    with patch(
        "cocli.application.reporting_service.get_campaign_dir", return_value=None
    ):
        with pytest.raises(ValueError, match="Campaign directory not found"):
            service._require_campaign_dir()
