"""Tests for job_run_service.py / ScrapeJobRun - the explicit trigger for
enqueuing new work into gm-list/pending/. See
cocli/models/campaigns/scrape_job_run.py for the design rationale: a run
is the only thing that can ever cause a re-enqueue - gm-list/pending/
draining to zero is never itself a trigger.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.application import job_run_service as jrs
from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager

US = "\x1f"


def _write_discovery_gen_file(campaign_dir: Path, shard: str, lat: str, lon: str, phrase: str) -> None:
    p = campaign_dir / "queues" / "discovery-gen" / "completed" / shard / lat / lon / f"{phrase}.usv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"dummy{US}scrape-task\n")


def _write_gm_list_receipt(campaign_dir: Path, shard: str, lat: str, lon: str, phrase: str) -> None:
    p = campaign_dir / "queues" / "gm-list" / "completed" / "results" / shard / lat / lon / f"{phrase}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}")


def test_create_job_run_writes_index_row_and_metadata(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        run = jrs.create_job_run("turboship", hostname="dev-machine")

        assert run.campaign_name == "turboship"
        assert run.id.endswith("_dev-machine")
        assert run.discovery_gen_completed_at is None
        assert run.started_at is None
        assert run.gm_list_completed_at is None

        index_rows = jrs._load_index("turboship")
        assert len(index_rows) == 1
        assert index_rows[0].id == run.id

        metadata_path = jrs._metadata_path("turboship", run.id)
        assert metadata_path.exists()
        assert run.id in metadata_path.read_text(encoding="utf-8")


def test_mark_discovery_gen_completed_snapshots_deduped_sorted_identities(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        run = jrs.create_job_run("turboship", hostname="dev-machine")

        # Duplicates should collapse; order shouldn't matter going in.
        identities = [
            "28.7/-96.9/rubber-flooring-contractor",
            "28.7/-96.9/sports-flooring-contractor",
            "28.7/-96.9/rubber-flooring-contractor",
        ]
        updated = jrs.mark_discovery_gen_completed(run, identities)

        assert updated.identity_count == 2
        assert updated.discovery_gen_completed_at is not None
        assert jrs.load_identities(updated) == [
            "28.7/-96.9/rubber-flooring-contractor",
            "28.7/-96.9/sports-flooring-contractor",
        ]

        # Persisted, not just returned - re-reading the index reflects it.
        reloaded = [r for r in jrs._load_index("turboship") if r.id == run.id][0]
        assert reloaded.identity_count == 2
        assert reloaded.discovery_gen_completed_at is not None


def test_enqueue_gm_list_for_run_copies_only_this_runs_scope(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        # Two discovery-gen items belong to this run; a third exists but
        # is NOT in this run's snapshot (e.g. a different/older run's
        # item) and must not get swept in.
        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "in-scope-a")
        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "in-scope-b")
        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "out-of-scope")

        run = jrs.create_job_run(campaign, hostname="dev-machine")
        run = jrs.mark_discovery_gen_completed(
            run,
            [
                "28.7/-96.9/in-scope-a",
                "28.7/-96.9/in-scope-b",
            ],
        )

        updated = jrs.enqueue_gm_list_for_run(run)

        assert updated.started_at is not None
        gm_list_q = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign)
        copied = sorted(p.name for p in gm_list_q.pending_dir.rglob("*.usv"))
        assert copied == ["in-scope-a.usv", "in-scope-b.usv"]


def test_enqueue_gm_list_for_run_skips_already_gm_list_completed_items(tmp_path: Path) -> None:
    """Idempotent: calling this twice (e.g. the resilience poller retrying
    a run that was interrupted mid-copy) must not re-copy an item that
    already has a gm-list completed receipt."""
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "already-done")
        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "still-pending")
        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "already-done")

        run = jrs.create_job_run(campaign, hostname="dev-machine")
        run = jrs.mark_discovery_gen_completed(
            run,
            ["28.7/-96.9/already-done", "28.7/-96.9/still-pending"],
        )

        jrs.enqueue_gm_list_for_run(run)

        gm_list_q = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign)
        copied = sorted(p.name for p in gm_list_q.pending_dir.rglob("*.usv"))
        assert copied == ["still-pending.usv"]


def test_check_and_mark_gm_list_completed_false_until_every_identity_resolved(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        run = jrs.create_job_run(campaign, hostname="dev-machine")
        run = jrs.mark_discovery_gen_completed(
            run, ["28.7/-96.9/item-a", "28.7/-96.9/item-b"]
        )

        # Only one of two resolved.
        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "item-a")

        result = jrs.check_and_mark_gm_list_completed(run)

        assert result is False
        reloaded = [r for r in jrs._load_index(campaign) if r.id == run.id][0]
        assert reloaded.gm_list_completed_at is None


def test_check_and_mark_gm_list_completed_true_when_all_resolved(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        run = jrs.create_job_run(campaign, hostname="dev-machine")
        run = jrs.mark_discovery_gen_completed(
            run, ["28.7/-96.9/item-a", "28.7/-96.9/item-b"]
        )

        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "item-a")
        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "item-b")

        result = jrs.check_and_mark_gm_list_completed(run)

        assert result is True
        reloaded = [r for r in jrs._load_index(campaign) if r.id == run.id][0]
        assert reloaded.gm_list_completed_at is not None


def test_list_open_job_runs_filters_to_runs_needing_poller_attention(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"

        # Not yet discovery_gen_completed - poller must leave it alone,
        # generation may still be in progress.
        mid_generation = jrs.create_job_run(campaign, hostname="dev-machine")

        # discovery_gen_completed_at set, started_at not - poller should
        # retry the auto-copy for this one.
        stuck_before_copy = jrs.create_job_run(campaign, hostname="dev-machine")
        stuck_before_copy = jrs.mark_discovery_gen_completed(
            stuck_before_copy, ["28.7/-96.9/x"]
        )

        # started_at set, gm_list_completed_at not - poller should check
        # completion for this one.
        draining = jrs.create_job_run(campaign, hostname="dev-machine")
        draining = jrs.mark_discovery_gen_completed(draining, ["28.7/-96.9/y"])
        draining = jrs.enqueue_gm_list_for_run(draining)

        # Fully resolved - poller has nothing left to do.
        campaign_dir = tmp_path / "campaigns" / campaign
        done = jrs.create_job_run(campaign, hostname="dev-machine")
        done = jrs.mark_discovery_gen_completed(done, ["28.7/-96.9/z"])
        done = jrs.enqueue_gm_list_for_run(done)
        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "z")
        jrs.check_and_mark_gm_list_completed(done)

        open_runs = {r.id for r in jrs.list_open_job_runs(campaign)}

        assert mid_generation.id not in open_runs
        assert stuck_before_copy.id in open_runs
        assert draining.id in open_runs
        assert done.id not in open_runs


def test_enqueue_gm_list_for_run_rescrape_all_copies_already_completed_items(
    tmp_path: Path,
) -> None:
    """Without rescrape_all, a fully-resolved run's own identities would
    all be filtered out as 'already scraped' (they trivially have
    receipts, or the run wouldn't be resolved) - rescrape_all bypasses
    that, which is what requeue_job_run() needs."""
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "item-a")
        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "item-a")

        run = jrs.create_job_run(campaign, hostname="dev-machine")
        run = jrs.mark_discovery_gen_completed(run, ["28.7/-96.9/item-a"])

        updated = jrs.enqueue_gm_list_for_run(run, rescrape_all=True)

        assert updated.started_at is not None
        gm_list_q = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign)
        copied = list(gm_list_q.pending_dir.rglob("*.usv"))
        assert len(copied) == 1


def test_requeue_job_run_creates_new_run_and_rescrapes_previous_identities(
    tmp_path: Path,
) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        campaign_dir = tmp_path / "campaigns" / campaign

        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "item-a")
        _write_discovery_gen_file(campaign_dir, "2", "28.7", "-96.9", "item-b")

        previous = jrs.create_job_run(campaign, hostname="dev-machine")
        previous = jrs.mark_discovery_gen_completed(
            previous, ["28.7/-96.9/item-a", "28.7/-96.9/item-b"]
        )
        previous = jrs.enqueue_gm_list_for_run(previous)
        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "item-a")
        _write_gm_list_receipt(campaign_dir, "2", "28.7", "-96.9", "item-b")
        jrs.check_and_mark_gm_list_completed(previous)

        new_run = jrs.requeue_job_run(campaign, previous.id, hostname="dev-machine")

        assert new_run.id != previous.id
        assert new_run.identity_count == 2
        assert new_run.started_at is not None
        assert jrs.load_identities(new_run) == jrs.load_identities(previous)

        gm_list_q = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign)
        copied = sorted(p.name for p in gm_list_q.pending_dir.rglob("*.usv"))
        assert copied == ["item-a.usv", "item-b.usv"]


def test_requeue_job_run_raises_for_unknown_previous_run(tmp_path: Path) -> None:
    import pytest

    with patch.object(paths, "root", tmp_path):
        with pytest.raises(ValueError, match="no-such-run"):
            jrs.requeue_job_run("turboship", "no-such-run")


def test_get_job_run_returns_none_when_not_found(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        assert jrs.get_job_run("turboship", "no-such-run") is None


def test_get_latest_job_run_returns_most_recently_created(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        campaign = "turboship"
        older = jrs.create_job_run(campaign, hostname="node-a")
        newer = jrs.create_job_run(campaign, hostname="node-b")

        latest = jrs.get_latest_job_run(campaign)

    assert latest is not None
    assert latest.id == newer.id
    assert latest.id != older.id


def test_get_latest_job_run_returns_none_for_empty_campaign(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        assert jrs.get_latest_job_run("brand-new") is None
