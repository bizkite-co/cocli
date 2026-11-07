"""Pi sync is complete only when every configured node synced."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from cocli.application.pi_sync_service import (
    PiSyncService,
    SyncResult,
    describe_sync_results,
)
from cocli.core.paths import paths
from cocli.core.queue.filesystem import ensure_lease_readable


def test_sync_is_incomplete_with_no_nodes() -> None:
    ok, detail = describe_sync_results([])
    assert not ok
    assert "No Pi nodes" in detail


def test_sync_is_incomplete_when_a_node_fails() -> None:
    ok, detail = describe_sync_results(
        [
            SyncResult(host="cocli5x0", success=False, files_synced=0, error="Connection timed out"),
            SyncResult(host="NUC01", success=True, files_synced=10),
        ]
    )
    assert not ok
    assert "cocli5x0: Connection timed out" in detail
    assert "Sync Complete" not in detail


def test_sync_names_the_queues_that_failed() -> None:
    ok, detail = describe_sync_results(
        [
            SyncResult(
                host="cocli5x0",
                success=False,
                files_synced=3,
                queue_results={"gm-list (completed/)": -1, "enrichment (completed/)": 3},
            )
        ]
    )
    assert not ok
    assert "gm-list (completed/)" in detail


def test_sync_is_complete_only_when_every_node_succeeds() -> None:
    ok, detail = describe_sync_results(
        [
            SyncResult(host="cocli5x0", success=True, files_synced=4),
            SyncResult(host="NUC01", success=True, files_synced=6),
        ]
    )
    assert ok
    assert detail == "2 nodes, 10 files"


def _one_node(tmp_path: Path) -> PiSyncService:
    paths.root = tmp_path
    node = MagicMock()
    node.hostname = "cocli5x0"
    node.ip_address = "100.1.1.1"
    return node


def test_queue_rsync_excludes_leases_and_does_not_kill_a_slow_copy(tmp_path: Path) -> None:
    node = _one_node(tmp_path)
    with patch("cocli.application.pi_sync_service.ClusterService") as cluster, patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="a/file.json\n", stderr=""),
    ) as run:
        cluster.return_value.get_nodes.return_value = [node]
        PiSyncService("turboship").sync_node("cocli5x0")

    cmd = run.call_args_list[0].args[0]
    assert "--exclude=lease.json" in cmd
    assert "--timeout=60" in cmd
    assert "timeout" not in run.call_args.kwargs
    assert cmd[-2].endswith("queues/gm-list/completed/")


def test_queue_rsync_failure_is_stored_on_the_result(tmp_path: Path) -> None:
    node = _one_node(tmp_path)
    with patch("cocli.application.pi_sync_service.ClusterService") as cluster, patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=23,
            stdout="",
            stderr="rsync: [sender] send_files failed to open \"lease.json\": Permission denied (13)\n",
        ),
    ):
        cluster.return_value.get_nodes.return_value = [node]
        result = PiSyncService("turboship").sync_completed()

    assert len(result) == 1
    assert not result[0].success
    assert result[0].error is not None
    assert "Permission denied" in result[0].error
    assert "gm-list (completed)" in result[0].error


def test_completed_sync_skips_pending(tmp_path: Path) -> None:
    node = _one_node(tmp_path)
    with patch("cocli.application.pi_sync_service.ClusterService") as cluster, patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ) as run:
        cluster.return_value.get_nodes.return_value = [node]
        PiSyncService("turboship").sync_completed()

    remotes = [call.args[0][-2] for call in run.call_args_list]
    assert remotes
    assert all(remote.endswith("completed/") for remote in remotes)
    assert not any("pending" in remote for remote in remotes)


def test_ensure_lease_readable_clears_a_root_only_mode(tmp_path: Path) -> None:
    lease = tmp_path / "lease.json"
    lease.write_text("{}", encoding="utf-8")
    os.chmod(lease, 0o600)
    ensure_lease_readable(lease)
    assert lease.stat().st_mode & 0o777 == 0o644


def test_email_index_sync_merges_without_delete(tmp_path: Path) -> None:
    paths.root = tmp_path
    node = MagicMock()
    node.hostname = "cocli5x0"
    node.ip_address = "100.1.1.1"
    with patch("cocli.application.pi_sync_service.ClusterService") as cluster, patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Number of regular files transferred: 12\n",
            stderr="",
        ),
    ) as run:
        cluster.return_value.get_nodes.return_value = [node]
        service = PiSyncService("turboship")
        results = service.sync_email_indexes()

    assert len(results) == 1
    assert results[0].success
    assert results[0].files_synced == 12
    cmd = run.call_args.args[0]
    assert "--delete" not in cmd
    assert "-auz" in cmd
    assert "--stats" in cmd
    assert cmd[-2].endswith("indexes/emails/")
    assert cmd[-1].endswith("indexes/emails/")
    assert "cocli5x0" not in cmd[-2] or "100.1.1.1" in cmd[-2]
