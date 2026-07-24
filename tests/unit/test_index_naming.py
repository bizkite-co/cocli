from pathlib import Path
from cocli.core.paths import paths

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.core.compact import CompactManager


def test_index_checkpoint_path_returns_prospects_usv(tmp_path: Path):
    index_paths = paths.campaign("test_campaign").index("google_maps_prospects")
    assert index_paths.checkpoint.name == "prospects.usv"


def test_compact_manager_uses_prospects_usv():
    manager = CompactManager("test_campaign", "google_maps_prospects")
    assert manager.checkpoint_path.name == "prospects.usv"


def test_google_maps_prospect_datapackage_resource_path():
    schema_fields = GoogleMapsProspect.get_datapackage_fields()
    assert len(schema_fields) == 56

    res_path = "prospects.usv"
    assert res_path == "prospects.usv"


def test_compact_manager_writes_datapackage_first(tmp_path: Path):
    paths.root = tmp_path
    manager = CompactManager("test_campaign", "google_maps_prospects")
    manager._write_schema_sidecar_first()

    datapackage_file = manager.index_dir / "datapackage.json"
    assert datapackage_file.exists()

