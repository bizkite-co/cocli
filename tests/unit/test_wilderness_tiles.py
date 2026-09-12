"""Global wilderness-tile index: mark/unmark and scrape skip."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from cocli.core.scrape_index import ScrapeIndex
from cocli.scrapers.google.gm_scraper.wilderness import WildernessManager


def test_mark_and_unmark_wilderness_tile(tmp_path: Path, mocker: Any) -> None:
    wilderness_dir = tmp_path / "indexes" / "wilderness-tiles"
    mocker.patch(
        "cocli.core.scrape_index.get_wilderness_tiles_index_dir",
        return_value=wilderness_dir,
    )
    mocker.patch(
        "cocli.core.scrape_index.get_scraped_areas_index_dir",
        return_value=tmp_path / "scraped_areas",
    )
    mocker.patch(
        "cocli.core.config.get_scraped_tiles_index_dir",
        return_value=tmp_path / "scraped-tiles",
    )

    index = ScrapeIndex()
    tile_id = "33.5_-116.0"
    assert index.is_wilderness_tile(tile_id) is False

    path = index.mark_wilderness_tile(tile_id, marked_by="test")
    assert path is not None
    assert path.exists()
    assert index.is_wilderness_tile(tile_id) is True
    assert "33.5_-116.0" in index.list_wilderness_tile_ids()

    assert index.unmark_wilderness_tile(tile_id) is True
    assert index.is_wilderness_tile(tile_id) is False


def test_should_scrape_skips_wilderness_grid_tile(tmp_path: Path, mocker: Any) -> None:
    wilderness_dir = tmp_path / "indexes" / "wilderness-tiles"
    mocker.patch(
        "cocli.core.scrape_index.get_wilderness_tiles_index_dir",
        return_value=wilderness_dir,
    )
    mocker.patch(
        "cocli.core.scrape_index.get_scraped_areas_index_dir",
        return_value=tmp_path / "scraped_areas",
    )
    mocker.patch(
        "cocli.core.config.get_scraped_tiles_index_dir",
        return_value=tmp_path / "scraped-tiles",
    )

    manager = WildernessManager()
    manager.index.mark_wilderness_tile("25.0_-80.0")
    bounds = {"lat_min": 25.0, "lat_max": 25.1, "lon_min": -80.0, "lon_max": -79.9}
    assert manager.should_scrape(bounds, "welders", tile_id="25.0_-80.0") is False
    assert manager.should_scrape(bounds, "welders", tile_id="25.1_-80.0") is True


def test_apply_wilderness_mark_uploads_to_campaign_s3(tmp_path: Path, mocker: Any) -> None:
    from cocli.application.worker_service import WorkerService

    wilderness_dir = tmp_path / "indexes" / "wilderness-tiles"
    mocker.patch(
        "cocli.core.scrape_index.get_wilderness_tiles_index_dir",
        return_value=wilderness_dir,
    )
    mocker.patch(
        "cocli.core.scrape_index.get_scraped_areas_index_dir",
        return_value=tmp_path / "scraped_areas",
    )
    mocker.patch(
        "cocli.core.config.get_scraped_tiles_index_dir",
        return_value=tmp_path / "scraped-tiles",
    )

    s3 = MagicMock()
    with patch.object(WorkerService, "_load_config"):
        service = WorkerService(campaign_name="turboship")
    service._apply_wilderness_mark("33.5_-116.0", True, s3)
    s3.upload_file.assert_called_once()
    args = s3.upload_file.call_args[0]
    assert args[1] == "cocli-data-turboship"
    assert "indexes/wilderness-tiles/33.5/-116.0/wilderness.usv" in args[2]

    service._apply_wilderness_mark("33.5_-116.0", False, s3)
    s3.delete_object.assert_called_once()
