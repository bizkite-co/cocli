# POLICY: frictionless-data-policy-enforcement
"""Path fidelity for DFQ local dirs and S3 keys (0010 PR2–PR6).

Golden strings must match production S3. Single path authority:
FilesystemQueue builders + per-queue StationDecl. Models that expose
get_s3_* / get_remote_key MUST agree with the queue for the same id.

Intentional exceptions (not base DFQ flat item paths):
- gm-list completed receipts: completed/results/{geo}/… (product)
- discovery-gen pool keys (PR7 station)
- enrichment completed S3: nested completed/{shard}/{domain}/task.json
  (local completed remains flat completed/{domain}.json)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cocli.core.queue.filesystem import (
    FilesystemEnrichmentQueue,
    FilesystemGmDetailsQueue,
    FilesystemGmListQueue,
    FilesystemQueue,
)
from cocli.core.sharding import get_domain_shard, get_shard_id
from cocli.models.campaigns.queues.enrichment import EnrichmentTask
from cocli.models.campaigns.queues.gm_details import GmItemTask


def test_gmlist_queue_path_fidelity(tmp_path: Path) -> None:
    """
    REPRODUCTION TEST: Detects double-sharding in FilesystemGmListQueue.
    If task_id is '2/25.0/-80.0/phrase.usv', the final path must NOT
    be 'pending/2/2/25.0/...'.
    """
    campaign = "test_campaign"
    with patch("cocli.core.paths.paths.root", tmp_path):
        queue = FilesystemGmListQueue(campaign)

        task_id = "2/25.0/-80.0/dentist.usv"

        task_dir = queue._get_task_dir(task_id)
        path_str = str(task_dir)

        assert "/2/2/" not in path_str, f"Double-sharding detected: {path_str}"
        assert path_str.endswith("pending/2/25.0/-80.0/dentist")

        s3_task = queue._get_s3_task_key(task_id)
        s3_lease = queue._get_s3_lease_key(task_id)
        assert (
            s3_task
            == f"campaigns/{campaign}/queues/gm-list/pending/2/25.0/-80.0/dentist/task.json"
        )
        assert (
            s3_lease
            == f"campaigns/{campaign}/queues/gm-list/pending/2/25.0/-80.0/dentist/lease.json"
        )
        assert "/2/2/" not in s3_task


def test_gmlist_result_key_via_layout(tmp_path: Path) -> None:
    campaign = "turboship"
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemGmListQueue(campaign)
        key = q._get_s3_gm_list_result_key("1", "18.1", "-66.0", "rubber-flooring")
        assert key == (
            f"campaigns/{campaign}/queues/gm-list/completed/results/"
            "1/18.1/-66.0/rubber-flooring.json"
        )
        assert key.startswith(q.layout.s3_prefix() + "/")


def test_generic_queue_sharding_fidelity(tmp_path: Path) -> None:
    """PlaceID-based tasks (gm-details) sharded exactly once via 6th char."""
    campaign = "test_campaign"
    with patch("cocli.core.paths.paths.root", tmp_path):
        queue = FilesystemQueue(campaign, "gm-details")

        task_id = "ChIJ-5-rest"

        task_dir = queue._get_task_dir(task_id)
        path_str = str(task_dir)

        assert "/pending/5/ChIJ-5-rest" in path_str
        assert "/pending/5/5/" not in path_str


def test_base_fsq_s3_keys_match_production_golden_strings(tmp_path: Path) -> None:
    """
    Golden keys: campaigns/{c}/queues/{q}/pending/{shard}/{id}/{task|lease}.json
    base completed/failed stay flat under phase (no shard).
    """
    campaign = "turboship"
    queue_name = "gm-details"
    task_id = "ChIJ-5-rest"
    shard = get_shard_id(task_id)
    assert shard == "5"

    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemQueue(campaign, queue_name)

        assert q.pending_dir.name == "pending"
        assert q.completed_dir.name == "completed"
        assert q.failed_dir.name == "failed"
        assert q.layout.phases.pending.name == "pending"

        rel = q._pending_rel(task_id)
        assert rel == f"pending/{shard}/{task_id}"
        assert q._get_task_dir(task_id) == q.layout.local_root / Path(rel)
        assert q._get_task_dir(task_id) == q.pending_dir / f"{shard}/{task_id}"

        s3_root = f"campaigns/{campaign}/queues/{queue_name}"
        assert q.layout.s3_prefix() == s3_root
        assert q._s3_pending_prefix() == f"{s3_root}/pending/"

        assert (
            q._get_s3_task_key(task_id)
            == f"{s3_root}/pending/{shard}/{task_id}/task.json"
        )
        assert (
            q._get_s3_lease_key(task_id)
            == f"{s3_root}/pending/{shard}/{task_id}/lease.json"
        )
        assert (
            q._get_s3_completed_key(task_id)
            == f"{s3_root}/completed/{task_id}.json"
        )
        assert q._get_s3_failed_key(task_id) == f"{s3_root}/failed/{task_id}.json"

        assert q._get_lease_path(task_id) == q._get_task_dir(task_id) / "lease.json"
        assert str(q._get_task_dir(task_id)).endswith(rel)


def test_enrichment_queue_domain_shard_s3_keys_unchanged(tmp_path: Path) -> None:
    """Subclass uses layout builders; domain-hash StationDecl."""
    campaign = "test_s3_campaign"
    domain = "example.com"
    shard = get_domain_shard(domain)

    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemEnrichmentQueue(campaign)

        assert (
            q._get_s3_task_key(domain)
            == f"campaigns/{campaign}/queues/enrichment/pending/{shard}/{domain}/task.json"
        )
        assert (
            q._get_s3_lease_key(domain)
            == f"campaigns/{campaign}/queues/enrichment/pending/{shard}/{domain}/lease.json"
        )
        # Nested completed (production)
        assert (
            q._get_s3_completed_key(domain)
            == f"campaigns/{campaign}/queues/enrichment/completed/{shard}/{domain}/task.json"
        )
        assert str(q._get_task_dir(domain)).endswith(f"pending/{shard}/{domain}")


def test_enrichment_model_agrees_with_queue(tmp_path: Path) -> None:
    """Model get_s3_* must not diverge from queue (single authority)."""
    campaign = "roadmap"
    domain = "ameripriseadvisors.com"
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemEnrichmentQueue(campaign)
        task = EnrichmentTask(
            domain=domain, company_slug="jack-venable", campaign_name=campaign
        )
        assert task.get_s3_task_key() == q._get_s3_task_key(domain)
        assert task.get_s3_lease_key() == q._get_s3_lease_key(domain)
        assert task.get_shard_id() == q._get_shard(domain) == get_domain_shard(domain)


def test_gm_details_model_agrees_with_queue(tmp_path: Path) -> None:
    campaign = "turboship"
    place_id = "ChIJ--Cy9B3Jw4kR9h1ar_qcBTg"
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemGmDetailsQueue(campaign)
        task = GmItemTask(place_id=place_id, campaign_name=campaign)
        assert task.get_remote_key() == q._get_s3_task_key(place_id)
        assert task.get_shard_id() == q._get_shard(place_id) == "-"


def test_layout_phase_dirs_equal_queue_base_children(tmp_path: Path) -> None:
    """QueueLayout phase_dir matches legacy queue_base / 'pending' shape."""
    campaign = "camp"
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemQueue(campaign, "gm-details")
        base = Path(str(q.queue_base.path))
        assert q.pending_dir == base / "pending"
        assert q.completed_dir == base / "completed"
        assert q.failed_dir == base / "failed"
        assert q.layout.local_root == base


def test_enrichment_ack_uploads_nested_completed_once(tmp_path: Path) -> None:
    """Ack must not double-write flat + nested; uses nested completed key only."""
    mock_s3 = MagicMock()
    campaign = "camp"
    domain = "example.com"
    with patch("cocli.core.paths.paths.root", tmp_path):
        q = FilesystemEnrichmentQueue(
            campaign, s3_client=mock_s3, bucket_name="b"
        )
        task_dir = q._get_task_dir(domain)
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text("{}")

        q.ack(domain)

        # upload_file(local, bucket, key)
        keys = [
            c.args[2]
            for c in mock_s3.upload_file.call_args_list
            if len(c.args) >= 3
        ]
        nested = q._get_s3_completed_key(domain)
        assert nested in keys
        flat = f"campaigns/{campaign}/queues/enrichment/completed/{domain}.json"
        assert flat not in keys
