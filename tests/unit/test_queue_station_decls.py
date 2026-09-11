"""0010 PR3: per-queue StationDecls preserve production shard algorithms."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.core.queue.filesystem import (
    FilesystemEnrichmentQueue,
    FilesystemGmDetailsQueue,
    FilesystemGmListQueue,
    FilesystemQueue,
)
from cocli.core.queue.layout import resolve_queue_station
from cocli.core.sharding import get_domain_shard, get_place_id_shard, get_shard_id
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from cocli.models.campaigns.queues.gm_list import ScrapeTask
from cocli.station_defs.campaigns.queues import (
    ENRICHMENT_QUEUE_STATION,
    GM_DETAILS_QUEUE_STATION,
    GM_LIST_QUEUE_STATION,
    GM_LIST_RESULTS_STATION,
    station_for_queue,
)
from stations.segments import collect_shard


def test_station_for_queue_mapping() -> None:
    from cocli.station_defs.campaigns.queues import MAP_TILE_QUEUE_STATION

    assert station_for_queue("gm-details") is GM_DETAILS_QUEUE_STATION
    assert station_for_queue("gm-list") is GM_LIST_QUEUE_STATION
    assert station_for_queue("enrichment") is ENRICHMENT_QUEUE_STATION
    assert station_for_queue("map-tile") is MAP_TILE_QUEUE_STATION
    from cocli.station_defs.campaigns.queues import (
        TO_CALL_INVALID_QUEUE_STATION,
        TO_CALL_QUEUE_STATION,
    )

    assert station_for_queue("to-call") is TO_CALL_QUEUE_STATION
    assert station_for_queue("to-call-invalid") is TO_CALL_INVALID_QUEUE_STATION
    from cocli.station_defs.campaigns.queues import TO_CALL_HIGH_VALUE_QUEUE_STATION

    assert station_for_queue("to-call-high-value") is TO_CALL_HIGH_VALUE_QUEUE_STATION
    from cocli.station_defs.campaigns.queues import (
        SCRAPED_EMAIL_INVALID_QUEUE_STATION,
    )

    assert (
        station_for_queue("scraped-email-invalid")
        is SCRAPED_EMAIL_INVALID_QUEUE_STATION
    )
    assert collect_shard(TO_CALL_QUEUE_STATION.segments) is None
    # unknown → place_id default
    assert collect_shard(station_for_queue("unknown-queue").segments) is not None
    assert (
        collect_shard(station_for_queue("unknown-queue").segments).shard_for(  # type: ignore[union-attr]
            "ChIJ-5-rest"
        )
        == "5"
    )


def test_place_id_combinator_matches_legacy_on_gm_details_decl() -> None:
    sh = collect_shard(GM_DETAILS_QUEUE_STATION.segments)
    assert sh is not None
    for key in (
        "ChIJ--Cy9B3Jw4kR9h1ar_qcBTg",
        "ChIJg_FAeU6P3YgRdYX05J1RuZw",
        "ChIJ-5-rest",
        "ChIJ5X0j7DHDwogRvQgaGw0y4FM",
        "short",
    ):
        assert sh.shard_for(key) == get_place_id_shard(key) == get_shard_id(key)


def test_domain_hash_combinator_matches_get_domain_shard() -> None:
    sh = collect_shard(ENRICHMENT_QUEUE_STATION.segments)
    assert sh is not None
    for domain in (
        "example.com",
        "agwfloors.com",
        "northerntool.com",
        "test.com",
    ):
        assert sh.shard_for(domain) == get_domain_shard(domain)


def test_gm_list_work_decl_is_not_gm_details_copy() -> None:
    """Pending gm-list is ScrapeTask USV with geo in the task id, not
    place-id json-file (the gm-details copy that GM_LIST_QUEUE_STATION was)."""
    assert GM_LIST_QUEUE_STATION.model is ScrapeTask
    assert GM_LIST_QUEUE_STATION.serialization == "usv"
    assert collect_shard(GM_LIST_QUEUE_STATION.segments) is None
    assert GM_DETAILS_QUEUE_STATION.serialization == "json-file"
    details_shard = collect_shard(GM_DETAILS_QUEUE_STATION.segments)
    assert details_shard is not None
    assert details_shard.shard_for("ChIJ-5-rest") == get_place_id_shard("ChIJ-5-rest")


def test_gm_list_results_station_is_list_item_usv_in_place() -> None:
    assert GM_LIST_RESULTS_STATION.model is GoogleMapsListItem
    assert GM_LIST_RESULTS_STATION.serialization == "usv"
    assert GM_LIST_RESULTS_STATION.datapackage_path == "datapackage.json"
    assert GM_LIST_RESULTS_STATION.path_template.endswith(
        "queues/gm-list/completed/results"
    )
    assert collect_shard(GM_LIST_RESULTS_STATION.segments) is None


def test_gm_list_layout_keeps_geo_pending_path() -> None:
    from cocli.core.queue.layout import task_rel_under_phase

    task_id = "3/33.4/-80.9/commercial-vinyl-flooring-contractor.usv"
    rel = task_rel_under_phase(GM_LIST_QUEUE_STATION, "pending", task_id)
    assert rel == "pending/3/33.4/-80.9/commercial-vinyl-flooring-contractor"
    # A leftover place-id combinator would still skip extra shard for this
    # pre-sharded id; the decl itself must not be that combinator.
    assert collect_shard(GM_LIST_QUEUE_STATION.segments) is None


def test_fsq_resolves_decl_and_shard_via_layout(tmp_path: Path) -> None:
    with patch("cocli.core.paths.paths.root", tmp_path):
        details = FilesystemGmDetailsQueue("camp")
        enrich = FilesystemEnrichmentQueue("camp")
        glist = FilesystemGmListQueue("camp")

        assert details.layout.station is resolve_queue_station("gm-details")
        assert enrich.layout.station is resolve_queue_station("enrichment")
        assert glist.layout.station is resolve_queue_station("gm-list")

        pid = "ChIJ--Cy9B3Jw4kR9h1ar_qcBTg"
        assert details._get_shard(pid) == "-"
        assert details._get_s3_task_key(pid).endswith(f"/pending/-/{pid}/task.json")

        domain = "example.com"
        dshard = get_domain_shard(domain)
        assert enrich._get_shard(domain) == dshard
        assert enrich._get_task_dir(domain).name == domain
        assert f"/pending/{dshard}/{domain}" in str(enrich._get_task_dir(domain))


def test_base_queue_unknown_name_uses_place_id_default(tmp_path: Path) -> None:
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemQueue("camp", "some-new-queue")
        assert q._get_shard("ChIJ-5-rest") == "5"
