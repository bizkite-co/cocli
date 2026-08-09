"""CLI wiring smoke tests for the two reconciliation commands:
`cocli audit queue mission-reconciliation` (gm-list-specific) and
`cocli data queue reconcile` (generic, any two directories).
"""

from pathlib import Path

from typer.testing import CliRunner

from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.commands.audit import app as audit_app
from cocli.commands.data import app as data_app

runner = CliRunner()


def _write(root: Path, rel_path: str) -> None:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("data")


def test_audit_queue_mission_reconciliation_cli(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign_name = "test-campaign"

    gm_list_queue = get_queue_manager(
        "gm-list", queue_type="gm-list", campaign_name=campaign_name
    )
    _write(gm_list_queue.target_tiles_dir, "1/10.0/-80.0/phrase-a.usv")
    _write(gm_list_queue.completed_dir / "results", "1/10.0/-80.0/phrase-a.json")

    result = runner.invoke(
        audit_app, ["queue", "mission-reconciliation", "--campaign", campaign_name]
    )

    assert result.exit_code == 0, result.output
    assert "Mission Reconciliation" in result.output
    assert "1" in result.output


def test_data_queue_reconcile_cli(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left, "1/10.0/-80.0/phrase-a.usv")
    _write(right, "9/10.0/-80.0/phrase-a.json")

    result = runner.invoke(data_app, ["queue", "reconcile", str(left), str(right)])

    assert result.exit_code == 0, result.output
    assert "Reconciliation" in result.output
