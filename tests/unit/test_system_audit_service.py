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
