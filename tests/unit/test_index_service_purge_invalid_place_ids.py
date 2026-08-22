"""Unit tests for IndexService.purge_invalid_place_ids: discards checkpoint
rows in the legacy Google CID place_id format (0x.../colon-containing),
which can never pass PlaceID validation - so IDENTITY SHIELD always
rejects them at GoogleMapsProspect.from_raw() regardless of how good the
underlying scrape was.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cocli.application.index_service import IndexService, PurgeInvalidPlaceIdsResult
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

US = "\x1f"


def _checkpoint_row(place_id: str) -> str:
    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    values = {f: "" for f in fieldnames}
    values["place_id"] = place_id
    return US.join(values[f] for f in fieldnames)


def _setup_campaign_dirs(tmp_path: Path, campaign: str = "test-campaign") -> None:
    paths.root = tmp_path
    (tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects").mkdir(parents=True)


def test_dry_run_reports_but_does_not_rewrite(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    checkpoint = tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects" / "prospects.usv"
    checkpoint.write_text(
        _checkpoint_row("ChIJValidPlaceIdAAAAAAAAAAAAA") + "\n"
        + _checkpoint_row("0x80c8c7adee37843f:0xfa88a0aebc400358") + "\n"
    )
    original_content = checkpoint.read_text()

    service = IndexService(campaign_name=campaign)
    with patch("cocli.core.compact.CompactManager") as mock_manager_cls:
        result = service.purge_invalid_place_ids(dry_run=True)

    assert isinstance(result, PurgeInvalidPlaceIdsResult)
    assert result.dry_run is True
    assert result.checkpoint_before == 2
    assert result.checkpoint_after == 1
    assert result.removed_place_ids == ["0x80c8c7adee37843f:0xfa88a0aebc400358"]
    assert checkpoint.read_text() == original_content  # untouched
    mock_manager_cls.assert_not_called()


def test_apply_rewrites_checkpoint_and_backs_up(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    index_dir = tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects"
    checkpoint = index_dir / "prospects.usv"
    checkpoint.write_text(
        _checkpoint_row("ChIJValidPlaceIdAAAAAAAAAAAAA") + "\n"
        + _checkpoint_row("0x80c8c7adee37843f:0xfa88a0aebc400358") + "\n"
        + _checkpoint_row("0x2cd407f20ab268d:0x6bc5d1a16716f9ed") + "\n"
    )

    service = IndexService(campaign_name=campaign)
    fake_manager = MagicMock()
    with patch("cocli.core.compact.CompactManager", return_value=fake_manager) as mock_manager_cls:
        result = service.purge_invalid_place_ids(dry_run=False)

    assert result.dry_run is False
    assert result.checkpoint_before == 3
    assert result.checkpoint_after == 1
    assert set(result.removed_place_ids) == {
        "0x80c8c7adee37843f:0xfa88a0aebc400358",
        "0x2cd407f20ab268d:0x6bc5d1a16716f9ed",
    }

    remaining = checkpoint.read_text().splitlines()
    assert len(remaining) == 1
    assert remaining[0].startswith("ChIJValidPlaceIdAAAAAAAAAAAAA")

    assert any(p.name != "prospects.usv" for p in index_dir.glob("prospects.usv*"))

    mock_manager_cls.assert_called_once_with(campaign_name=campaign, index_name="google_maps_prospects")
    fake_manager.commit_remote.assert_called_once()


def test_apply_with_no_invalid_rows_does_not_touch_checkpoint(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    checkpoint = tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects" / "prospects.usv"
    checkpoint.write_text(_checkpoint_row("ChIJValidPlaceIdAAAAAAAAAAAAA") + "\n")
    original_content = checkpoint.read_text()

    service = IndexService(campaign_name=campaign)
    with patch("cocli.core.compact.CompactManager") as mock_manager_cls:
        result = service.purge_invalid_place_ids(dry_run=False)

    assert result.removed_place_ids == []
    assert checkpoint.read_text() == original_content
    mock_manager_cls.assert_not_called()


def test_no_checkpoint_returns_empty_result(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)

    service = IndexService(campaign_name=campaign)
    result = service.purge_invalid_place_ids(dry_run=True)

    assert result.checkpoint_before == 0
    assert result.checkpoint_after == 0
    assert result.removed_place_ids == []
