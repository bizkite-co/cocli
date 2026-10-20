"""Pi sync is complete only when every configured node synced."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from cocli.application.pi_sync_service import PiSyncService, SyncResult, describe_sync_results
from cocli.core.paths import paths


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
