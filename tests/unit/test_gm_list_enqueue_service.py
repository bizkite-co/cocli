"""enqueue_unscraped_to_gm_list_pending: copies discovery-gen/completed/ into
gm-list/pending/ - a real, transformation-free file copy (both sides are
ScrapeTask-shaped at the same relative path), filtered by the reconcile
tool's unscraped set unless --rescrape-all. See task-agent ticket
gm-list-queue-regressed-from-pendingcompleted-pattern-diverged-from-its-own-stations-declaration,
"Goal-state decision v2".
"""

from pathlib import Path
from unittest.mock import patch

from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.application.gm_list_enqueue_service import enqueue_unscraped_to_gm_list_pending


def _write(root: Path, rel_path: str) -> None:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("row\n")


def test_copies_only_unscraped_items_by_default(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        discovery_gen_completed = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
        gm_list_queue = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name)

        _write(discovery_gen_completed, "2/28.7/-96.9/phrase-a.usv")
        _write(discovery_gen_completed, "2/28.7/-96.9/phrase-b.usv")
        # phrase-a already has a receipt - should be skipped.
        _write(gm_list_queue.completed_dir / "results", "2/28.7/-96.9/phrase-a.json")

        result = enqueue_unscraped_to_gm_list_pending(campaign_name)

        assert result.candidates == 1
        assert result.copied == 1
        assert result.skipped_already_scraped == 1
        assert (gm_list_queue.pending_dir / "2/28.7/-96.9/phrase-b.usv").exists()
        assert not (gm_list_queue.pending_dir / "2/28.7/-96.9/phrase-a.usv").exists()


def test_copy_is_byte_identical_at_same_relative_path(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        discovery_gen_completed = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
        gm_list_queue = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name)

        source = discovery_gen_completed / "3" / "40.0" / "-75.0" / "phrase-c.usv"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("28.7\x1f-96.9\x1fphrase-c\n")

        enqueue_unscraped_to_gm_list_pending(campaign_name)

        dest = gm_list_queue.pending_dir / "3" / "40.0" / "-75.0" / "phrase-c.usv"
        assert dest.read_text() == source.read_text()


def test_rescrape_all_copies_already_scraped_items_too(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        discovery_gen_completed = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
        gm_list_queue = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name)

        _write(discovery_gen_completed, "2/28.7/-96.9/phrase-a.usv")
        _write(gm_list_queue.completed_dir / "results", "2/28.7/-96.9/phrase-a.json")

        result = enqueue_unscraped_to_gm_list_pending(campaign_name, rescrape_all=True)

        assert result.candidates == 1
        assert result.copied == 1
        assert result.skipped_already_scraped == 0
        assert (gm_list_queue.pending_dir / "2/28.7/-96.9/phrase-a.usv").exists()


def test_limit_bounds_the_batch_deterministically(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        discovery_gen_completed = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
        gm_list_queue = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name)

        for phrase in ["phrase-a", "phrase-b", "phrase-c"]:
            _write(discovery_gen_completed, f"2/28.7/-96.9/{phrase}.usv")

        result = enqueue_unscraped_to_gm_list_pending(campaign_name, limit=2)

        assert result.candidates == 3
        assert result.copied == 2
        copied_files = sorted(p.name for p in gm_list_queue.pending_dir.rglob("*.usv"))
        assert copied_files == ["phrase-a.usv", "phrase-b.usv"]


def test_dry_run_writes_nothing(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign_name = "test-campaign"
        discovery_gen_completed = paths.campaign(campaign_name).queue("discovery-gen").state("completed")
        gm_list_queue = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name)

        _write(discovery_gen_completed, "2/28.7/-96.9/phrase-a.usv")

        result = enqueue_unscraped_to_gm_list_pending(campaign_name, dry_run=True)

        assert result.copied == 1
        assert result.dry_run is True
        assert list(gm_list_queue.pending_dir.rglob("*.usv")) == []
