import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.core.paths import paths

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.core.compact import CompactManager


def test_index_checkpoint_path_returns_prospects_usv(tmp_path: Path) -> None:
    index_paths = paths.campaign("test_campaign").index("google_maps_prospects")
    assert index_paths.checkpoint.name == "prospects.usv"


def test_compact_manager_uses_prospects_usv() -> None:
    manager = CompactManager("test_campaign", "google_maps_prospects")
    assert manager.checkpoint_path.name == "prospects.usv"


def test_google_maps_prospect_datapackage_resource_path() -> None:
    schema_fields = GoogleMapsProspect.get_datapackage_fields()
    assert len(schema_fields) == 57
    # Append-only: category is the newest field and must stay LAST so
    # legacy 56-column rows keep parsing positionally.
    assert schema_fields[-1]["name"] == "category"

    res_path = "prospects.usv"
    assert res_path == "prospects.usv"


def test_compact_manager_writes_datapackage_first(tmp_path: Path) -> None:
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager._write_schema_sidecar_first()

    datapackage_file = manager.index_dir / "datapackage.json"
    assert datapackage_file.exists()


def test_acquire_staging_raises_on_sync_failure(tmp_path: Path) -> None:
    """Regression: a failed `aws s3 sync` used to be logged and swallowed, so
    merge() saw an empty local_proc_dir and treated a real isolated batch as
    "nothing to merge" - silently re-committing the unchanged checkpoint and,
    once cleanup() ran, permanently deleting the batch from S3 with the CLI
    reporting success throughout. It must propagate so the caller's
    except/finally aborts before merge/commit/cleanup run."""
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")

    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(255, ["aws", "s3", "sync"]),
    ):
        with pytest.raises(subprocess.CalledProcessError):
            manager.acquire_staging()

