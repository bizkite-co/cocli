"""Unit tests for CompactManager: Pi-direct WAL staging, stale-lock CAS
takeover/resume, and stations C9 conformance (no source deletion before
commit_remote() succeeds).

Split out of a production incident (2026-08-13): pi_sync_service.py deleted
its rsynced-from-Pi local WAL copy the moment an S3 push succeeded, not the
moment compaction actually committed - so two consecutive credential-timeout
failures during `cocli index compact` each left a real batch stranded in S3
processing/{run_id}/ with no way back to it. See task-agent ticket
compact-wal-staging-violates-stations-c9-deletes-pi-sourced-data-before-commit-orphans-batches-on-failure
and ~/repos/stations/spec/CONCURRENCY.md §3 (C6-C14, especially C9)."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from cocli.core.compact import LOCK_STALE_SECONDS, CompactManager
from cocli.core.paths import paths
from cocli.models.campaigns.worker_config import PiNodeConfig


def _node(hostname: str, ip_address: Optional[str] = None) -> PiNodeConfig:
    return PiNodeConfig(host=hostname, ip=ip_address)


def _rsync_side_effect(files_by_host: Dict[str, int]) -> Any:
    """subprocess.run side_effect simulating rsync writing N fake WAL files
    per host into the destination the real code passed it."""

    def _run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "rsync"
        remote = cmd[2]
        dest = Path(cmd[3].rstrip("/"))
        host = remote.split("@")[1].split(":")[0]
        dest.mkdir(parents=True, exist_ok=True)
        for i in range(files_by_host.get(host, 0)):
            (dest / f"{host}_{i}.usv").write_text("row\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return _run


# ---------------------------------------------------------------------------
# isolate_wal(): Pi-direct staging, multi-node aggregation, no premature delete
# ---------------------------------------------------------------------------


def test_isolate_wal_stages_multiple_nodes_into_run_batch(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    nodes = [_node("cocli5x0"), _node("cocli5x1")]

    with patch("subprocess.run", side_effect=_rsync_side_effect({"cocli5x0": 2, "cocli5x1": 3})):
        staged = manager.isolate_wal(nodes=nodes)

    assert staged == 5
    assert len(list((manager.local_proc_dir / "cocli5x0").glob("*.usv"))) == 2
    assert len(list((manager.local_proc_dir / "cocli5x1").glob("*.usv"))) == 3


def test_isolate_wal_skips_node_with_nothing_new(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    nodes = [_node("cocli5x0"), _node("cocli5x1")]

    with patch("subprocess.run", side_effect=_rsync_side_effect({"cocli5x0": 1, "cocli5x1": 0})):
        staged = manager.isolate_wal(nodes=nodes)

    assert staged == 1
    assert not (manager.local_proc_dir / "cocli5x1").exists()


def test_isolate_wal_continues_past_one_nodes_rsync_failure(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    nodes = [_node("cocli5x0"), _node("cocli5x1")]

    def _run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        remote = cmd[2]
        host = remote.split("@")[1].split(":")[0]
        if host == "cocli5x0":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="connection refused")
        dest = Path(cmd[3].rstrip("/"))
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "seg.usv").write_text("row\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=_run):
        staged = manager.isolate_wal(nodes=nodes)

    assert staged == 1
    assert not (manager.local_proc_dir / "cocli5x0").exists()
    assert (manager.local_proc_dir / "cocli5x1" / "seg.usv").exists()


def test_isolate_wal_leaves_local_wal_and_naked_root_untouched(tmp_path: Path) -> None:
    """The exact defect this ticket fixes, second instance: naked-root USVs
    and index_dir/wal are legitimate fold sources
    (stations_runtime._collect_prospect_usv_sources scans both directly) -
    isolate_wal() must count them, never delete them before a commit."""
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager.index_dir.mkdir(parents=True, exist_ok=True)
    wal_dir = manager.index_dir / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    (wal_dir / "seg1.usv").write_text("row\n")
    naked = manager.index_dir / "naked.usv"
    naked.write_text("row\n")

    staged = manager.isolate_wal(nodes=[])

    assert staged == 2
    assert (wal_dir / "seg1.usv").exists()
    assert naked.exists()


# ---------------------------------------------------------------------------
# cleanup(): only ever called after commit - purges sources, S3 only when
# this run actually used the legacy S3 staging path
# ---------------------------------------------------------------------------


def test_cleanup_purges_local_sources_without_touching_s3(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager.index_dir.mkdir(parents=True, exist_ok=True)
    wal_dir = manager.index_dir / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    (wal_dir / "seg1.usv").write_text("row\n")
    naked = manager.index_dir / "naked.usv"
    naked.write_text("row\n")
    manager.local_proc_dir.mkdir(parents=True, exist_ok=True)
    (manager.local_proc_dir / "cocli5x0").mkdir(parents=True, exist_ok=True)

    with patch("subprocess.run") as mock_run:
        manager.cleanup()

    mock_run.assert_not_called()
    assert not naked.exists()
    assert not (wal_dir / "seg1.usv").exists()
    assert wal_dir.exists()  # recreated empty, ready for the next cycle
    assert not manager.local_proc_dir.exists()


def test_cleanup_removes_s3_prefix_only_when_recovery_path_used(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager._used_s3_staging = True
    manager.local_proc_dir.mkdir(parents=True, exist_ok=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0)
        manager.cleanup()

    mock_run.assert_called_once()
    cmd = mock_run.call_args.args[0]
    assert cmd[:3] == ["aws", "s3", "rm"]


# ---------------------------------------------------------------------------
# acquire_lock(): create-if-absent, refuse a live lock, CAS-takeover + resume
# a stale one (stations C2/C3)
# ---------------------------------------------------------------------------


def test_acquire_lock_succeeds_when_absent(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager._s3 = MagicMock()

    assert manager.acquire_lock() is True
    kwargs = manager._s3.put_object.call_args.kwargs
    assert kwargs["IfNoneMatch"] == "*"


def test_acquire_lock_refuses_when_live_lock_exists(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager._s3 = MagicMock()
    manager._s3.put_object.side_effect = [
        ClientError({"Error": {"Code": "PreconditionFailed", "Message": "x"}}, "PutObject"),
    ]
    live_lock = json.dumps({
        "run_id": "run_live",
        "created_at": datetime.now(UTC).isoformat(),
        "host": "other-host",
    })
    manager._s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=live_lock.encode())),
        "ETag": '"abc"',
    }

    assert manager.acquire_lock() is False
    # Only the initial create-if-absent attempt - no takeover of a live lock.
    assert manager._s3.put_object.call_count == 1


def test_acquire_lock_takes_over_stale_lock_and_resumes_local_batch(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager._s3 = MagicMock()
    manager._s3.put_object.side_effect = [
        ClientError({"Error": {"Code": "PreconditionFailed", "Message": "x"}}, "PutObject"),
        {},
    ]
    stale_created_at = (
        datetime.now(UTC) - timedelta(seconds=LOCK_STALE_SECONDS + 60)
    ).isoformat()
    stale_lock = json.dumps({
        "run_id": "run_crashed",
        "created_at": stale_created_at,
        "host": "other-host",
    })
    manager._s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=stale_lock.encode())),
        "ETag": '"deadbeef"',
    }

    # A crashed prior run's local batch, still sitting on this machine.
    recovered_dir = manager.index_dir / "processing" / "run_crashed"
    (recovered_dir / "cocli5x0").mkdir(parents=True, exist_ok=True)
    (recovered_dir / "cocli5x0" / "seg.usv").write_text("row\n")

    assert manager.acquire_lock() is True
    assert manager.run_id == "run_crashed"
    assert manager.local_proc_dir == recovered_dir

    # CAS-replace, never delete-then-create (stations C3).
    second_call_kwargs = manager._s3.put_object.call_args_list[1].kwargs
    assert second_call_kwargs["IfMatch"] == '"deadbeef"'


def test_acquire_lock_starts_fresh_when_stale_lock_has_no_local_batch(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    original_run_id = manager.run_id
    manager._s3 = MagicMock()
    manager._s3.put_object.side_effect = [
        ClientError({"Error": {"Code": "PreconditionFailed", "Message": "x"}}, "PutObject"),
        {},
    ]
    stale_created_at = (
        datetime.now(UTC) - timedelta(seconds=LOCK_STALE_SECONDS + 60)
    ).isoformat()
    stale_lock = json.dumps({
        "run_id": "run_crashed_elsewhere",
        "created_at": stale_created_at,
        "host": "other-host",
    })
    manager._s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=stale_lock.encode())),
        "ETag": '"deadbeef"',
    }

    assert manager.acquire_lock() is True
    # No local batch for the crashed run's id on this machine - a fresh
    # run_id is fine; the take-over itself (liveness) still succeeded.
    assert manager.run_id == original_run_id


def test_acquire_lock_returns_false_when_stale_takeover_loses_the_race(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager._s3 = MagicMock()
    manager._s3.put_object.side_effect = [
        ClientError({"Error": {"Code": "PreconditionFailed", "Message": "x"}}, "PutObject"),
        ClientError({"Error": {"Code": "PreconditionFailed", "Message": "x"}}, "PutObject"),
    ]
    stale_created_at = (
        datetime.now(UTC) - timedelta(seconds=LOCK_STALE_SECONDS + 60)
    ).isoformat()
    stale_lock = json.dumps({
        "run_id": "run_crashed",
        "created_at": stale_created_at,
        "host": "other-host",
    })
    manager._s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=stale_lock.encode())),
        "ETag": '"deadbeef"',
    }

    assert manager.acquire_lock() is False
