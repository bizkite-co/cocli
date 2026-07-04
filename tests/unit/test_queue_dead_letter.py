import pytest
from unittest.mock import MagicMock, patch
from cocli.core.queue.filesystem import FilesystemEnrichmentQueue
from cocli.models.campaigns.queues.base import QueueMessage


@pytest.fixture
def mock_s3():
    return MagicMock()


def test_nack_below_threshold_stays_pending(tmp_path, mock_s3):
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test_campaign"
        bucket = "test-bucket"
        domain = "flaky-domain.com"

        q = FilesystemEnrichmentQueue(campaign, s3_client=mock_s3, bucket_name=bucket, max_nack_attempts=5)
        task = QueueMessage(domain=domain, company_slug="flaky", campaign_name=campaign)
        task_id = q.push(task)

        task_dir = q._get_task_dir(task_id)

        for _ in range(4):
            q.nack(task_id)

        # Still under threshold: task.json remains in pending, not dead-lettered.
        assert (task_dir / "task.json").exists()
        assert not (q.failed_dir / f"{task_id}.json").exists()


def test_nack_at_threshold_dead_letters_task(tmp_path, mock_s3):
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test_campaign"
        bucket = "test-bucket"
        domain = "poison-domain.com"

        q = FilesystemEnrichmentQueue(campaign, s3_client=mock_s3, bucket_name=bucket, max_nack_attempts=3)
        task = QueueMessage(domain=domain, company_slug="poison", campaign_name=campaign)
        task_id = q.push(task)

        task_dir = q._get_task_dir(task_id)

        q.nack(task_id)
        q.nack(task_id)
        assert (task_dir / "task.json").exists()

        q.nack(task_id)  # 3rd nack hits the threshold

        # Pending task dir is gone; task moved to failed/.
        assert not task_dir.exists()
        assert (q.failed_dir / f"{task_id}.json").exists()

        # S3: failed copy uploaded, pending task+lease keys deleted.
        mock_s3.upload_file.assert_any_call(
            str(q.failed_dir / f"{task_id}.json"),
            bucket,
            f"campaigns/{campaign}/queues/enrichment/failed/{task_id}.json",
        )
        mock_s3.delete_objects.assert_called()


def test_dead_lettered_task_not_polled_again(tmp_path, mock_s3):
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test_campaign"
        bucket = "test-bucket"
        domain = "poison-domain-2.com"

        q = FilesystemEnrichmentQueue(campaign, s3_client=mock_s3, bucket_name=bucket, max_nack_attempts=1)
        task = QueueMessage(domain=domain, company_slug="poison2", campaign_name=campaign)
        task_id = q.push(task)

        q.nack(task_id)  # threshold=1, dead-letters immediately

        # No local candidates left, and S3 discovery finds nothing new either
        # (mock_s3 has no real objects), so poll returns empty.
        mock_s3.get_paginator.return_value.paginate.return_value = []
        tasks = q.poll(batch_size=1)
        assert tasks == []
