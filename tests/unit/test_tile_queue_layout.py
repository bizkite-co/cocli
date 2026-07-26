"""0010 PR5: map-tile StationDecl — processing as phase, tiles as layout under pending."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cocli.core.queue.filesystem import FilesystemTileQueue
from cocli.station_defs.campaigns.queues import (
    MAP_TILE_PENDING_LAYOUT,
    MAP_TILE_QUEUE_STATION,
    station_for_queue,
)
from stations.segments import collect_phases, collect_shard


def test_map_tile_station_phases_and_no_shard() -> None:
    ph = collect_phases(MAP_TILE_QUEUE_STATION.segments)
    assert ph is not None
    assert ph.pending.name == "pending"
    assert ph.processing.name == "processing"
    assert ph.completed.name == "completed"
    # tiles is layout, not a declared phase
    assert not hasattr(ph, "tiles") or getattr(ph, "tiles", None) is None
    assert collect_shard(MAP_TILE_QUEUE_STATION.segments) is None
    assert station_for_queue("map-tile") is MAP_TILE_QUEUE_STATION
    assert MAP_TILE_PENDING_LAYOUT == "tiles"


def test_tile_queue_phase_dirs_and_tiles_layout(tmp_path: Path) -> None:
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemTileQueue("camp")

        base = Path(str(q.queue_base.path))
        assert q.layout.station is MAP_TILE_QUEUE_STATION
        assert q.pending_dir == base / "pending"
        assert q.processing_dir == base / "processing"
        assert q.completed_dir == base / "completed"
        # Layout bag under pending — not queue_base/tiles
        assert q.tiles_dir == base / "pending" / "tiles"
        assert q.tiles_dir == q.pending_dir / MAP_TILE_PENDING_LAYOUT
        assert q.tiles_dir.exists()

        # PhaseRef names, not ad-hoc peer of pending
        assert q.processing_dir.name == "processing"
        assert q.processing_dir.parent == base


def test_tile_queue_s3_completed_key(tmp_path: Path) -> None:
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemTileQueue("turboship")
        key = q._get_s3_completed_key("tile-1.usv")
        assert key == (
            "campaigns/turboship/queues/map-tile/completed/tile-1.usv"
        )
        assert key.startswith(q.layout.s3_prefix() + "/")


def test_tile_ack_uses_layout_s3_key(tmp_path: Path) -> None:
    mock_s3 = MagicMock()
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemTileQueue(
            "camp", s3_client=mock_s3, bucket_name="b"
        )
        q.processing_dir.mkdir(parents=True, exist_ok=True)
        tile = q.processing_dir / "t1.usv"
        tile.write_text("row\n")

        q.ack(tile)

        assert (q.completed_dir / "t1.usv").exists()
        mock_s3.put_object.assert_called()
        kwargs = mock_s3.put_object.call_args.kwargs
        assert kwargs["Key"] == q._get_s3_completed_key("t1.usv")
