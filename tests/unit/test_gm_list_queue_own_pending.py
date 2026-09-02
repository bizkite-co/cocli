"""FilesystemGmListQueue: poll()/ack()/push() only ever touch gm-list's own
pending_dir/completed_dir (fixed 2026-08-09) - previously poll() read
directly from a foreign queue's directory (discovery-gen/completed) and
gated leasing on a broken witness-file lookup. See task-agent ticket
gm-list-queue-regressed-from-pendingcompleted-pattern-diverged-from-its-own-stations-declaration.
"""

from unittest.mock import MagicMock, patch

from cocli.core.paths import paths
from cocli.core.queue.filesystem import FilesystemGmListQueue
from cocli.models.campaigns.queues.gm_list import ScrapeTask


def test_poll_never_reads_discovery_gen_completed(tmp_path):
    """A file sitting in discovery-gen/completed/ (a foreign queue's
    directory) must never surface via poll() - only gm-list/pending/ does."""
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign = "test-campaign"
        q = FilesystemGmListQueue(campaign)

        discovery_gen_completed = paths.campaign(campaign).queue("discovery-gen").state("completed")
        foreign = discovery_gen_completed / "2" / "29.5" / "-98.5" / "dentist.usv"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_text("29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000")

        tasks = q.poll(batch_size=10)

        assert tasks == []


def test_poll_no_longer_gates_on_witness_files(tmp_path):
    """Dedup is the copy step's job now, not poll()'s - a witness file for
    an item sitting in pending/ must not block it from being leased."""
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign = "test-campaign"
        q = FilesystemGmListQueue(campaign)

        task_id = "2/29.5/-98.5/dentist.usv"
        pending_file = q.pending_dir / task_id
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text("29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000")

        # A witness file at the path the old (deleted) witness-check used.
        from cocli.core.config import get_cocli_base_dir

        witness = get_cocli_base_dir() / "indexes" / "scraped-tiles" / task_id
        witness.parent.mkdir(parents=True, exist_ok=True)
        witness.write_text("2026-08-09T00:00:00+00:00\x1f1\x1fworker-1")

        tasks = q.poll(batch_size=10)

        assert len(tasks) == 1
        assert tasks[0].search_phrase == "dentist"


def test_discover_mission_from_s3_removed(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemGmListQueue("test-campaign")
        assert not hasattr(q, "_discover_mission_from_s3")
        assert not hasattr(q, "target_tiles_dir")
        assert not hasattr(q, "witness_dir")


def test_push_writes_into_gm_lists_own_pending_not_discovery_gen(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign = "test-campaign"
        q = FilesystemGmListQueue(campaign)

        task = ScrapeTask(
            latitude=29.5, longitude=-98.5, zoom=15.0,
            search_phrase="dentist", campaign_name=campaign,
        )

        task_id = q.push(task)

        assert (q.pending_dir / task_id).exists()
        discovery_gen_completed = paths.campaign(campaign).queue("discovery-gen").state("completed")
        assert not (discovery_gen_completed / task_id).exists()


def test_ack_deletes_source_pending_file_and_leaves_discovery_gen_untouched(tmp_path):
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign = "test-campaign"
        q = FilesystemGmListQueue(campaign)

        task_id = "2/29.5/-98.5/dentist.usv"
        pending_file = q.pending_dir / task_id
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text("29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000")

        # A file at the same relative path under discovery-gen/completed,
        # representing that stage's own, separate, permanent output -
        # ack() must never touch it.
        discovery_gen_completed = paths.campaign(campaign).queue("discovery-gen").state("completed")
        source = discovery_gen_completed / task_id
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000")

        tasks = q.poll(batch_size=1)
        assert len(tasks) == 1
        task = tasks[0]

        q.ack(task)

        assert not pending_file.exists()
        assert source.exists()
        assert (q.completed_dir / "results" / "2" / "29.5" / "-98.5" / "dentist.json").exists()


def test_ack_deletes_s3_mirror_of_pending_task(tmp_path):
    mock_s3 = MagicMock()
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign = "test-campaign"
        q = FilesystemGmListQueue(campaign, s3_client=mock_s3, bucket_name="b")

        task_id = "2/29.5/-98.5/dentist.usv"
        pending_file = q.pending_dir / task_id
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text("29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000")

        tasks = q.poll(batch_size=1)
        task = tasks[0]

        q.ack(task)

        deleted_keys = {c.kwargs["Key"] for c in mock_s3.delete_object.call_args_list}
        assert q._get_s3_pending_task_key(task_id) in deleted_keys


def test_nack_below_threshold_leaves_pending_usv(tmp_path):
    """Reproduction: gm-list nack must not look for task.json. Under the
    threshold the flat .usv stays in pending/ and failed/ stays empty."""
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign = "test-campaign"
        q = FilesystemGmListQueue(campaign, max_nack_attempts=3)

        task_id = "2/29.5/-98.5/dentist.usv"
        pending_file = q.pending_dir / task_id
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text("29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000")

        tasks = q.poll(batch_size=1)
        assert len(tasks) == 1

        q.nack(tasks[0])
        q.nack(tasks[0])

        assert pending_file.exists()
        assert not (q.failed_dir / task_id).exists()
        assert list(q.failed_dir.rglob("*.usv")) == []
        assert list(q.failed_dir.rglob("*.json")) == []


def test_nack_at_threshold_dead_letters_flat_usv_with_reconcile_identity(tmp_path):
    """Drive nack() past max_nack_attempts: the pending .usv moves to
    failed/ at the same relative path (not {task_id}.json), and
    identities_with_paths sees {lat}/{lon}/{phrase}."""
    from cocli.core.queue.reconcile import identities_with_paths

    mock_s3 = MagicMock()
    with patch("cocli.core.paths.paths.root", tmp_path):
        campaign = "test-campaign"
        q = FilesystemGmListQueue(
            campaign, s3_client=mock_s3, bucket_name="b", max_nack_attempts=3
        )

        task_id = "2/29.5/-98.5/dentist.usv"
        pending_file = q.pending_dir / task_id
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        body = "29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000"
        pending_file.write_text(body)

        tasks = q.poll(batch_size=1)
        task = tasks[0]

        q.nack(task)
        q.nack(task)
        assert pending_file.exists()

        q.nack(task)

        failed_file = q.failed_dir / task_id
        assert not pending_file.exists()
        assert failed_file.is_file()
        assert failed_file.read_text() == body
        assert not (q.failed_dir / f"{task_id}.json").exists()
        assert not q._get_task_dir(task_id).exists()

        ids = identities_with_paths(q.failed_dir)
        assert "29.5/-98.5/dentist" in ids
        assert ids["29.5/-98.5/dentist"] == failed_file

        mock_s3.upload_file.assert_any_call(
            str(failed_file),
            "b",
            q._get_s3_gm_list_failed_key(task_id),
        )
        deleted = mock_s3.delete_objects.call_args.kwargs["Delete"]["Objects"]
        deleted_keys = {obj["Key"] for obj in deleted}
        assert q._get_s3_pending_task_key(task_id) in deleted_keys
        assert q._get_s3_lease_key(task_id) in deleted_keys

        mock_s3.get_paginator.return_value.paginate.return_value = []
        assert q.poll(batch_size=10) == []
