"""QueueLayout: local Path and S3 keys share one relative path (0010 PR1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cocli.core.queue.layout import QueueLayout, task_rel_under_phase
from cocli.core.sharding import get_place_id_shard, get_shard_id
from cocli.station_defs.campaigns.queues import DFQ_QUEUE_STATION
from stations.segments import collect_shard, shard_by_char_index


def test_place_id_combinator_matches_legacy_get_shard_id() -> None:
    s = shard_by_char_index(5)
    for key in ("ChIJ-5-rest", "ChIJabcdef", "short", "ChIJ0xxxxx", "ab"):
        assert s.shard_for(key) == get_place_id_shard(key), key
        assert s.shard_for(key) == get_shard_id(key), key
    assert collect_shard(DFQ_QUEUE_STATION.segments) is not None
    assert collect_shard(DFQ_QUEUE_STATION.segments).shard_for(  # type: ignore[union-attr]
        "ChIJ-5-rest"
    ) == get_shard_id("ChIJ-5-rest")


def test_local_and_s3_share_relative_suffix(tmp_path: Path) -> None:
    layout = QueueLayout(
        station=DFQ_QUEUE_STATION,
        campaign_name="camp",
        queue_name="gm-details",
        local_root=tmp_path / "queues" / "gm-details",
    )
    ph = layout.phases
    task_id = "ChIJ-5-rest"
    rel = layout.relative_item(ph.pending, task_id)
    local = layout.item_dir(ph.pending, task_id)
    s3_prefix = layout.s3_item_prefix(ph.pending, task_id)
    s3_task = layout.s3_task_key(ph.pending, task_id)
    s3_lease = layout.s3_lease_key(ph.pending, task_id)

    assert rel == f"pending/{get_shard_id(task_id)}/{task_id}"
    assert local == layout.local_root / Path(rel)
    assert s3_prefix.endswith("/" + rel)
    assert s3_prefix == f"campaigns/camp/queues/gm-details/{rel}"
    assert s3_task == f"{s3_prefix}/task.json"
    assert s3_lease == f"{s3_prefix}/lease.json"
    # same relative for local lease
    assert layout.local_lease_path(ph.pending, task_id) == local / "lease.json"


def test_pre_sharded_task_id_not_double_sharded() -> None:
    rel = task_rel_under_phase(
        DFQ_QUEUE_STATION, "pending", "2/25.0/-80.0/dentist.usv"
    )
    assert rel == "pending/2/25.0/-80.0/dentist"
    assert "/2/2/" not in rel


def test_unknown_phase_rejected(tmp_path: Path) -> None:
    layout = QueueLayout(
        station=DFQ_QUEUE_STATION,
        campaign_name="c",
        queue_name="q",
        local_root=tmp_path,
    )
    with pytest.raises(ValueError, match="not in declared"):
        layout.relative_item("not-a-phase", "ChIJ-5-rest")


def test_phase_ref_token_works(tmp_path: Path) -> None:
    layout = QueueLayout(
        station=DFQ_QUEUE_STATION,
        campaign_name="c",
        queue_name="q",
        local_root=tmp_path,
    )
    ph = layout.phases
    rel = layout.relative_item(ph.completed, "ChIJ-5-rest")
    assert rel.startswith("completed/")
