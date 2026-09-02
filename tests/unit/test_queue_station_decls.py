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
from cocli.station_defs.campaigns.queues import (
    ENRICHMENT_QUEUE_STATION,
    GM_DETAILS_QUEUE_STATION,
    GM_LIST_QUEUE_STATION,
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
