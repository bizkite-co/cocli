"""Unit tests for IndexService.clean_quote_corruption: strips residual
literal double-quote corruption left over from before commit 931cc4ec
fixed the compaction fold's missing quote='' (data-quality-incidents/001).
Single-quotes/apostrophes must never be touched - they're routinely real
content in a business name or address (data-quality-incidents/002).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cocli.application.index_service import CleanQuoteCorruptionResult, IndexService
from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

US = "\x1f"


def _checkpoint_row(place_id: str, **overrides: str) -> str:
    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    values = {f: "" for f in fieldnames}
    values["place_id"] = place_id
    values.update(overrides)
    return US.join(values[f] for f in fieldnames)


def _setup_campaign_dirs(tmp_path: Path, campaign: str = "test-campaign") -> None:
    paths.root = tmp_path
    (tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects").mkdir(parents=True)


def test_dry_run_reports_but_does_not_rewrite(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    checkpoint = (
        tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects" / "prospects.usv"
    )
    checkpoint.write_text(
        _checkpoint_row("ChIJClean", name="Acme Corp") + "\n"
        + _checkpoint_row(
            "ChIJDirty", name='"""Acme Corp"""', full_address='"""1501 Heritage Pkwy"""'
        ) + "\n",
        encoding="utf-8",
    )
    original_content = checkpoint.read_text()

    service = IndexService(campaign_name=campaign)
    with patch("cocli.core.compact.CompactManager") as mock_manager_cls:
        result = service.clean_quote_corruption(dry_run=True)

    assert isinstance(result, CleanQuoteCorruptionResult)
    assert result.dry_run is True
    assert result.checkpoint_total == 2
    assert result.rows_cleaned == 1
    assert result.fields_affected["name"] == 1
    assert result.fields_affected["full_address"] == 1
    assert "ChIJDirty" in result.sample_place_ids
    assert checkpoint.read_text() == original_content  # untouched
    mock_manager_cls.assert_not_called()


def test_apply_strips_double_quotes_but_preserves_apostrophes(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    index_dir = tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects"
    checkpoint = index_dir / "prospects.usv"
    checkpoint.write_text(
        _checkpoint_row(
            "ChIJDirty", name='"""Acme Corp"""', full_address='"""1501 Heritage Pkwy"""'
        ) + "\n"
        + _checkpoint_row("ChIJApostrophe", name="John's Flooring Inc.") + "\n",
        encoding="utf-8",
    )

    service = IndexService(campaign_name=campaign)
    fake_manager = MagicMock()
    with patch("cocli.core.compact.CompactManager", return_value=fake_manager) as mock_manager_cls:
        result = service.clean_quote_corruption(dry_run=False)

    assert result.dry_run is False
    assert result.rows_cleaned == 1

    fieldnames = list(GoogleMapsProspect.model_fields.keys())
    name_idx = fieldnames.index("name")
    addr_idx = fieldnames.index("full_address")

    lines = checkpoint.read_text().splitlines()
    dirty_row = next(ln for ln in lines if ln.startswith("ChIJDirty" + US))
    apostrophe_row = next(ln for ln in lines if ln.startswith("ChIJApostrophe" + US))

    assert dirty_row.split(US)[name_idx] == "Acme Corp"
    assert dirty_row.split(US)[addr_idx] == "1501 Heritage Pkwy"
    assert apostrophe_row.split(US)[name_idx] == "John's Flooring Inc.", (
        "apostrophe must survive untouched"
    )

    assert any(p.name != "prospects.usv" for p in index_dir.glob("prospects.usv*"))
    mock_manager_cls.assert_called_once_with(campaign_name=campaign, index_name="google_maps_prospects")
    fake_manager.commit_remote.assert_called_once()


def test_apply_with_nothing_to_clean_is_a_no_op(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)
    checkpoint = (
        tmp_path / "campaigns" / campaign / "indexes" / "google_maps_prospects" / "prospects.usv"
    )
    checkpoint.write_text(
        _checkpoint_row("ChIJClean", name="John's Flooring") + "\n", encoding="utf-8"
    )
    original_content = checkpoint.read_text()

    service = IndexService(campaign_name=campaign)
    with patch("cocli.core.compact.CompactManager") as mock_manager_cls:
        result = service.clean_quote_corruption(dry_run=False)

    assert result.rows_cleaned == 0
    assert checkpoint.read_text() == original_content
    mock_manager_cls.assert_not_called()


def test_no_checkpoint_returns_empty_result(tmp_path: Path) -> None:
    campaign = "test-campaign"
    _setup_campaign_dirs(tmp_path, campaign)

    service = IndexService(campaign_name=campaign)
    result = service.clean_quote_corruption(dry_run=True)

    assert result.checkpoint_total == 0
    assert result.rows_cleaned == 0
