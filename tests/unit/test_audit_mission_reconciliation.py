"""AuditService.audit_mission_reconciliation: reconciles gm-list's mission
pool (discovery-gen/completed), pending, and receipts by identity - the
tool built to replace ad hoc `comm` one-liners after the gm-list
pending/completed regression investigation (task-agent ticket
gm-list-queue-regressed-from-pendingcompleted-pattern-diverged-from-its-own-stations-declaration).
"""

from pathlib import Path

from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.application.audit_service import AuditService


def _write(root: Path, rel_path: str) -> None:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("data")


def test_audit_mission_reconciliation(tmp_path: Path) -> None:
    paths.root = tmp_path
    campaign_name = "test-campaign"

    gm_list_queue = get_queue_manager(
        "gm-list", queue_type="gm-list", campaign_name=campaign_name
    )
    mission_dir = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
    receipts_dir = gm_list_queue.completed_dir / "results"
    pending_dir = gm_list_queue.pending_dir

    # 3 mission tiles; 2 have receipts (one under a different shard bucket -
    # bucket is not part of identity), 1 does not (still unscraped).
    _write(mission_dir, "1/10.0/-80.0/phrase-a.usv")
    _write(mission_dir, "2/10.0/-80.0/phrase-b.usv")
    _write(mission_dir, "1/10.0/-80.0/phrase-c.usv")
    _write(receipts_dir, "9/10.0/-80.0/phrase-a.json")
    _write(receipts_dir, "2/10.0/-80.0/phrase-b.json")
    # An orphaned receipt with no matching mission tile at all.
    _write(receipts_dir, "1/50.0/-50.0/phrase-orphan.json")

    # 2 pending files: one already has a receipt (stale, safe to purge),
    # one genuinely has no receipt yet (truly pending).
    _write(pending_dir, "1/10.0/-80.0/phrase-a.usv")
    _write(pending_dir, "1/20.0/-90.0/phrase-d.usv")

    service = AuditService(campaign_name=campaign_name)
    result = service.audit_mission_reconciliation(campaign_name)

    assert result.mission_total == 3
    assert result.receipt_total == 3
    assert result.unscraped_count == 1
    assert result.unscraped_ids == ["10.0/-80.0/phrase-c"]
    assert result.orphaned_receipt_count == 1
    assert result.orphaned_receipt_ids == ["50.0/-50.0/phrase-orphan"]

    assert result.pending_total == 2
    assert result.stale_pending_count == 1
    assert result.stale_pending_ids == ["10.0/-80.0/phrase-a"]
    assert result.truly_pending_count == 1
    assert result.truly_pending_ids == ["20.0/-90.0/phrase-d"]
