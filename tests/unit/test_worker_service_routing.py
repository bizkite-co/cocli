"""route_discovered_list_item: the gm-list scraper's per-discovery routing
decision, extracted from _run_scrape_task_loop so it's testable without a
Playwright browser.

Pins the fix for the domain-bypass gap: bypassing gm-details must not also
skip the WAL write gm-details would otherwise have made (see task-agent
ticket wire-gm-list-data-into-prospects-compaction-deprioritize-gm-details).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from cocli.application.worker_service import route_discovered_list_item
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem

_PLACE_ID = "ChIJ" + "y" * 22


def _make_item(**overrides: Any) -> GoogleMapsListItem:
    data = {
        "place_id": _PLACE_ID,
        "company_slug": "test-flooring-co",
        "name": "Test Flooring Co",
        "category": "Flooring contractor",
    }
    data.update(overrides)
    return GoogleMapsListItem.model_validate(data)


def test_domain_present_bypasses_details_and_writes_wal(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    item = _make_item(domain="testflooring.com")
    enrichment_queue = MagicMock()
    gm_list_item_queue = MagicMock()

    route_discovered_list_item(
        item,
        campaign_name="t",
        enrichment_queue=enrichment_queue,
        gm_list_item_queue=gm_list_item_queue,
        processed_by="test-worker",
    )

    gm_list_item_queue.push.assert_not_called()
    enrichment_queue.push.assert_called_once()
    pushed = enrichment_queue.push.call_args[0][0]
    assert pushed.domain == "testflooring.com"
    assert pushed.company_slug == "test-flooring-co"
    assert pushed.campaign_name == "t"

    from cocli.core.prospects_csv_manager import ProspectsIndexManager
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

    wal_path = ProspectsIndexManager("t").get_file_path(_PLACE_ID, for_write=True)
    assert wal_path.exists(), "domain-bypass must still write a durable WAL record"
    prospect = GoogleMapsProspect.from_usv(wal_path.read_text(encoding="utf-8"))
    assert prospect.place_id == _PLACE_ID
    assert prospect.slug == "test-flooring-co"
    assert prospect.category == "Flooring contractor"
    assert prospect.processed_by == "test-worker"


def test_domain_present_propagates_job_run_id_to_enrichment_task(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    item = _make_item(domain="testflooring.com")
    enrichment_queue = MagicMock()
    gm_list_item_queue = MagicMock()

    route_discovered_list_item(
        item,
        campaign_name="t",
        enrichment_queue=enrichment_queue,
        gm_list_item_queue=gm_list_item_queue,
        processed_by="test-worker",
        job_run_id="20260829T120000000000Z_dev-machine",
    )

    pushed = enrichment_queue.push.call_args[0][0]
    assert pushed.job_run_id == "20260829T120000000000Z_dev-machine"


def test_no_domain_queues_for_details_and_writes_no_wal(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    item = _make_item()  # no domain
    enrichment_queue = MagicMock()
    gm_list_item_queue = MagicMock()

    route_discovered_list_item(
        item,
        campaign_name="t",
        enrichment_queue=enrichment_queue,
        gm_list_item_queue=gm_list_item_queue,
        processed_by="test-worker",
    )

    enrichment_queue.push.assert_not_called()
    gm_list_item_queue.push.assert_called_once()
    pushed_task = gm_list_item_queue.push.call_args[0][0]
    assert pushed_task.place_id == _PLACE_ID

    from cocli.core.prospects_csv_manager import ProspectsIndexManager

    wal_path = ProspectsIndexManager("t").get_file_path(_PLACE_ID, for_write=True)
    assert not wal_path.exists(), (
        "no-domain items are gm-details' responsibility to persist once it "
        "finds a domain - the bypass path must not write a WAL record for them"
    )


def test_no_domain_propagates_job_run_id_to_gm_item_task(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    item = _make_item()  # no domain
    enrichment_queue = MagicMock()
    gm_list_item_queue = MagicMock()

    route_discovered_list_item(
        item,
        campaign_name="t",
        enrichment_queue=enrichment_queue,
        gm_list_item_queue=gm_list_item_queue,
        processed_by="test-worker",
        job_run_id="20260829T120000000000Z_dev-machine",
    )

    pushed_task = gm_list_item_queue.push.call_args[0][0]
    assert pushed_task.job_run_id == "20260829T120000000000Z_dev-machine"


def test_job_run_id_defaults_to_none_when_not_provided(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from cocli.core import paths as paths_mod

    monkeypatch.setattr(paths_mod.paths, "root", tmp_path)

    item = _make_item()
    enrichment_queue = MagicMock()
    gm_list_item_queue = MagicMock()

    route_discovered_list_item(
        item,
        campaign_name="t",
        enrichment_queue=enrichment_queue,
        gm_list_item_queue=gm_list_item_queue,
        processed_by="test-worker",
    )

    pushed_task = gm_list_item_queue.push.call_args[0][0]
    assert pushed_task.job_run_id is None
