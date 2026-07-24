"""Unit tests for IndexService (index status, datapackage, compact orchestration)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from cocli.application.index_service import (
    CompactResult,
    DomainBackfillResult,
    IndexService,
    IndexStatusReport,
    WriteDatapackageResult,
    setup_index_log_file,
)
from cocli.core.paths import paths
from cocli.models.base import SchemaConflictError


def test_setup_index_log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    log_file = setup_index_log_file("roadmap", "google_maps_prospects")
    assert log_file.parent.name == ".logs"
    assert "compact_roadmap_google_maps_prospects_" in log_file.name
    assert log_file.parent.exists()


def test_resolve_index_dir_domains(tmp_path: Path) -> None:
    paths.root = tmp_path
    service = IndexService(campaign_name="test-campaign")
    assert service.resolve_index_dir("domains") == tmp_path / "indexes" / "domains"


def test_resolve_index_dir_requires_campaign(tmp_path: Path) -> None:
    paths.root = tmp_path
    service = IndexService(campaign_name="")
    with pytest.raises(ValueError, match="Campaign required"):
        service.resolve_index_dir("google_maps_prospects")


def test_resolve_index_dir_campaign_scoped(tmp_path: Path) -> None:
    paths.root = tmp_path
    service = IndexService(campaign_name="roadmap")
    target = service.resolve_index_dir("google_maps_prospects")
    assert "roadmap" in str(target)
    assert "google_maps_prospects" in str(target) or "indexes" in str(target)


def test_write_datapackage_unknown_index() -> None:
    service = IndexService(campaign_name="roadmap")
    with pytest.raises(ValueError, match="Unknown index type: not-a-real-index") as exc:
        service.write_datapackage("not-a-real-index")
    # Must be ValueError so CLI str(e) is clean (KeyError adds repr quotes).
    assert str(exc.value) == "Unknown index type: not-a-real-index"


def test_write_datapackage_creates_dir_and_calls_model(
    tmp_path: Path,
) -> None:
    paths.root = tmp_path
    service = IndexService(campaign_name="roadmap")
    mock_model = MagicMock()
    with patch.object(
        IndexService, "index_model_map", return_value={"domains": mock_model}
    ):
        result = service.write_datapackage("domains", force=False)

    assert isinstance(result, WriteDatapackageResult)
    assert result.index_name == "domains"
    assert result.target_dir == tmp_path / "indexes" / "domains"
    assert result.target_dir.exists()
    assert result.resource_name == "domains"
    assert result.resource_path == "*.usv"
    mock_model.save_datapackage.assert_called_once_with(
        result.target_dir, "domains", "*.usv", force=False
    )


def test_write_datapackage_google_maps_resource_path(
    tmp_path: Path,
) -> None:
    paths.root = tmp_path
    service = IndexService(campaign_name="roadmap")
    mock_model = MagicMock()

    # Stub resolve so we do not depend on IndexPaths layout details
    target = tmp_path / "camp" / "indexes" / "google_maps_prospects"
    with (
        patch.object(
            IndexService, "index_model_map", return_value={"google_maps_prospects": mock_model}
        ),
        patch.object(IndexService, "resolve_index_dir", return_value=target),
    ):
        result = service.write_datapackage("google_maps_prospects", force=True)

    assert result.resource_path == "prospects.usv"
    mock_model.save_datapackage.assert_called_once_with(
        target, "google-maps-prospects", "prospects.usv", force=True
    )



def test_write_datapackage_propagates_schema_conflict(tmp_path: Path) -> None:
    paths.root = tmp_path
    service = IndexService(campaign_name="roadmap")
    mock_model = MagicMock()
    mock_model.save_datapackage.side_effect = SchemaConflictError(
        "drift", diff=["field a -> b"]
    )
    with patch.object(
        IndexService, "index_model_map", return_value={"domains": mock_model}
    ):
        with pytest.raises(SchemaConflictError) as exc:
            service.write_datapackage("domains")
    assert "field a -> b" in exc.value.diff


def _make_compact_manager_mock(
    *,
    lock_ok: bool = True,
    moved: int = 1,
    lock_body: bytes | None = None,
    wal_keys: List[str] | None = None,
    proc_keys: List[str] | None = None,
    checkpoint: Dict[str, Any] | None = None,
    interrupted_prefixes: List[str] | None = None,
) -> MagicMock:
    manager = MagicMock()
    manager._bucket = "test-bucket"
    manager.s3_lock_key = "campaigns/c/indexes/i/compact.lock"
    manager.s3_wal_prefix = "campaigns/c/indexes/i/wal/"
    manager.s3_index_prefix = "campaigns/c/indexes/i/"
    manager.s3_proc_prefix = "campaigns/c/indexes/i/processing/run_x/"
    manager.index_dir = Path("/tmp/index")
    manager.local_proc_dir = Path("/tmp/index/processing/run_x")
    manager.acquire_lock.return_value = lock_ok
    manager.isolate_wal.return_value = moved

    # S3 client + exceptions
    s3 = MagicMock()
    no_such = type("NoSuchKey", (Exception,), {})
    s3.exceptions = SimpleNamespace(NoSuchKey=no_such)
    manager.s3 = s3

    if lock_body is not None:
        s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=lock_body))}
    else:
        s3.get_object.side_effect = no_such()

    wal_keys = wal_keys if wal_keys is not None else []
    proc_keys = proc_keys if proc_keys is not None else []
    interrupted_prefixes = interrupted_prefixes if interrupted_prefixes is not None else []

    def paginate(**kwargs: Any) -> List[Dict[str, Any]]:
        prefix = kwargs.get("Prefix", "")
        if "Delimiter" in kwargs and prefix.endswith("processing/"):
            return [
                {
                    "CommonPrefixes": [
                        {"Prefix": p} for p in interrupted_prefixes
                    ]
                }
            ]
        if prefix.endswith("wal/"):
            return [
                {
                    "Contents": [
                        {"Key": k} for k in wal_keys
                    ]
                }
            ] if wal_keys else [{}]
        if "processing/" in prefix:
            return [{"Contents": [{"Key": k} for k in proc_keys]}] if proc_keys else [{}]
        return [{}]

    s3.get_paginator.return_value.paginate.side_effect = paginate

    if checkpoint is None:
        s3.head_object.side_effect = no_such()
    else:
        s3.head_object.return_value = checkpoint

    return manager


def test_get_status_empty_index() -> None:
    manager = _make_compact_manager_mock()
    service = IndexService(campaign_name="roadmap")
    with patch(
        "cocli.core.compact.CompactManager", return_value=manager
    ):
        report = service.get_status("google_maps_prospects")

    assert isinstance(report, IndexStatusReport)
    assert report.campaign_name == "roadmap"
    assert report.index_name == "google_maps_prospects"
    assert report.lock.active is False
    assert report.wal_backlog_count == 0
    assert report.processing_file_count == 0
    assert report.checkpoint.found is False


def test_get_status_with_lock_wal_and_checkpoint() -> None:
    from datetime import datetime, timezone

    lock_json = b'{"run_id":"run_1","created_at":"t0","host":"host-a"}'
    manager = _make_compact_manager_mock(
        lock_body=lock_json,
        wal_keys=[
            "campaigns/c/indexes/i/wal/a.usv",
            "campaigns/c/indexes/i/wal/b.csv",
            "campaigns/c/indexes/i/wal/skip.txt",
        ],
        proc_keys=["campaigns/c/indexes/i/processing/run_1/x.usv"],
        checkpoint={
            "ContentLength": 2 * 1024 * 1024,
            "LastModified": datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        },
    )
    service = IndexService(campaign_name="roadmap")
    with patch("cocli.core.compact.CompactManager", return_value=manager):
        report = service.get_status("google_maps_prospects")

    assert report.lock.active is True
    assert report.lock.run_id == "run_1"
    assert report.lock.host == "host-a"
    assert report.wal_backlog_count == 2
    assert report.processing_file_count == 1
    assert report.checkpoint.found is True
    assert report.checkpoint.size_mb == pytest.approx(2.0)


def test_list_interrupted_runs() -> None:
    manager = _make_compact_manager_mock(
        interrupted_prefixes=[
            "campaigns/c/indexes/i/processing/run_abc/",
            "campaigns/c/indexes/i/processing/run_def/",
        ]
    )
    service = IndexService(campaign_name="roadmap")
    with patch("cocli.core.compact.CompactManager", return_value=manager):
        runs = service.list_interrupted_runs("google_maps_prospects")
    assert runs == ["run_abc", "run_def"]


def test_compact_lock_failure() -> None:
    manager = _make_compact_manager_mock(lock_ok=False)
    service = IndexService(campaign_name="roadmap")
    with (
        patch.object(IndexService, "list_interrupted_runs", return_value=[]),
        patch("cocli.core.compact.CompactManager", return_value=manager),
    ):
        result = service.compact("google_maps_prospects")

    assert isinstance(result, CompactResult)
    assert result.success is False
    assert "Lock" in result.message
    manager.release_lock.assert_not_called()


def test_compact_success_path() -> None:
    manager = _make_compact_manager_mock(lock_ok=True, moved=3)
    service = IndexService(campaign_name="roadmap")
    steps: list[str] = []
    with (
        patch.object(IndexService, "list_interrupted_runs", return_value=[]),
        patch("cocli.core.compact.CompactManager", return_value=manager),
    ):
        result = service.compact(
            "google_maps_prospects",
            log_file=Path("/tmp/x.log"),
            log_callback=steps.append,
        )

    assert result.success is True
    assert result.isolated_files == 3
    manager.acquire_staging.assert_called_once()
    manager.merge.assert_called_once()
    manager.commit_remote.assert_called_once()
    manager.cleanup.assert_called_once()
    manager.release_lock.assert_called_once()
    # Live progress steps restored (cluster log_callback idiom).
    assert "Checking for interrupted runs..." in steps
    assert "Acquiring S3 lock..." in steps
    assert "Isolating WAL files on S3..." in steps
    assert "Downloading staging data..." in steps
    assert "Merging via stations commit path (DuckDB fold + CURRENT CAS)..." in steps
    assert "Uploading new checkpoint to S3..." in steps
    assert "Cleaning up..." in steps


def test_compact_nothing_to_do() -> None:
    manager = _make_compact_manager_mock(lock_ok=True, moved=0)
    service = IndexService(campaign_name="roadmap")
    with (
        patch.object(IndexService, "list_interrupted_runs", return_value=[]),
        patch("cocli.core.compact.CompactManager", return_value=manager),
    ):
        result = service.compact("google_maps_prospects")

    assert result.success is True
    assert result.isolated_files == 0
    assert result.message == "Nothing to compact."
    manager.merge.assert_not_called()
    manager.release_lock.assert_called_once()


def test_compact_recovers_interrupted_runs() -> None:
    manager = _make_compact_manager_mock(lock_ok=True, moved=1)
    service = IndexService(campaign_name="roadmap")
    with (
        patch.object(
            IndexService, "list_interrupted_runs", return_value=["run_old"]
        ),
        patch.object(IndexService, "recover_interrupted_run") as recover,
        patch("cocli.core.compact.CompactManager", return_value=manager),
    ):
        result = service.compact("google_maps_prospects")

    recover.assert_called_once()
    assert result.recovered_runs == ["run_old"]
    assert result.success is True


def test_backfill_domains() -> None:
    mock_campaign = MagicMock()
    mock_manager = MagicMock()
    mock_manager.backfill_from_companies.return_value = 7

    service = IndexService(campaign_name="roadmap")
    with (
        patch(
            "cocli.models.campaigns.campaign.Campaign.load",
            return_value=mock_campaign,
        ),
        patch(
            "cocli.core.config.load_campaign_config",
            return_value={"campaign": {"tag": "turboship"}},
        ),
        patch(
            "cocli.core.domain_index_manager.DomainIndexManager",
            return_value=mock_manager,
        ),
    ):
        result = service.backfill_domains(limit=10, compact=True)

    assert isinstance(result, DomainBackfillResult)
    assert result.records_added == 7
    assert result.tag == "turboship"
    assert result.compacted is True
    mock_manager.backfill_from_companies.assert_called_once_with("turboship", limit=10)
    mock_manager.compact_inbox.assert_called_once()


def test_backfill_domains_skips_compact_when_empty() -> None:
    mock_campaign = MagicMock()
    mock_manager = MagicMock()
    mock_manager.backfill_from_companies.return_value = 0

    service = IndexService(campaign_name="roadmap")
    with (
        patch(
            "cocli.models.campaigns.campaign.Campaign.load",
            return_value=mock_campaign,
        ),
        patch(
            "cocli.core.config.load_campaign_config",
            return_value={},
        ),
        patch(
            "cocli.core.domain_index_manager.DomainIndexManager",
            return_value=mock_manager,
        ),
    ):
        result = service.backfill_domains(compact=True)

    assert result.records_added == 0
    assert result.compacted is False
    assert result.tag == "roadmap"
    mock_manager.compact_inbox.assert_not_called()
