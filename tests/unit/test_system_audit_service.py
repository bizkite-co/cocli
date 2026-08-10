import json

from cocli.core.paths import paths
from cocli.application.audit_service import AuditService


def test_get_cli_tree():
    from typer.main import get_command
    from cocli.main import app as main_app
    click_command = get_command(main_app)
    service = AuditService(campaign_name="test-campaign")
    tree = service.get_cli_tree(click_command)
    assert isinstance(tree, str)
    assert len(tree) > 0
    assert "cocli" in tree
    assert "audit" in tree


def test_audit_filesystem_empty(tmp_path):
    # Setup isolated paths.root
    paths.root = tmp_path
    service = AuditService(campaign_name="test-campaign")
    res = service.audit_filesystem(campaign_name="test-campaign")
    assert "root_node" in res
    assert "orphans" in res
    assert len(res["orphans"]) == 0


def test_audit_schemas_detects_missing_hash(tmp_path):
    # Setup isolated paths.root
    paths.root = tmp_path

    # Create a mock campaign folder and a datapackage.json file without a schema hash
    campaign_dir = paths.campaign("test-campaign").ensure()
    dp_file = campaign_dir / "datapackage.json"
    dp_file.parent.mkdir(parents=True, exist_ok=True)
    dp_file.write_text(
        json.dumps({"name": "test-resource", "resources": []}), encoding="utf-8"
    )

    service = AuditService(campaign_name="test-campaign")
    res = service.audit_schemas(campaign="test-campaign")

    assert res["files_checked"] == 1
    assert len(res["issues_found"]) == 1
    assert res["issues_found"][0]["issue"] == "MISSING_SCHEMA_HASH"


def test_get_tile_status_counts_sharded_files_recursively(tmp_path):
    """map-tile's real writer (populate_tile_queue) shards pending/completed
    as {shard}/{lat}/{lon}/{tile_id}.usv, not a flat directory - a flat glob
    against that shape always returned 0. Regression test for that fix."""
    paths.root = tmp_path
    from cocli.core.queue.factory import get_queue_manager

    tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name="test-campaign")

    pending_file = tile_queue.pending_dir / "2" / "28.7" / "-96.9" / "28.7_-96.9.usv"
    pending_file.parent.mkdir(parents=True, exist_ok=True)
    pending_file.write_text("row\n")

    completed_file = tile_queue.completed_dir / "3" / "33.5" / "-86.6" / "33.5_-86.6.usv"
    completed_file.parent.mkdir(parents=True, exist_ok=True)
    completed_file.write_text("row\n")

    service = AuditService(campaign_name="test-campaign")
    res = service.get_tile_status("test-campaign")

    assert res.pending_count == 1
    assert res.completed_count == 1
    assert not hasattr(res, "processing_count")
