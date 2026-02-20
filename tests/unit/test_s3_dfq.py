import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, UTC, timedelta
from cocli.core.queue.filesystem import FilesystemEnrichmentQueue
from cocli.models.campaigns.queues.base import QueueMessage

@pytest.fixture
def mock_s3():
    return MagicMock()

def test_s3_conditional_lease_success(tmp_path, mock_s3):
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test_s3_campaign"
        bucket = "test-bucket"
        domain = "example.com"
        
        q = FilesystemEnrichmentQueue(campaign, s3_client=mock_s3, bucket_name=bucket)
        
        task = QueueMessage(
            domain=domain,
            company_slug="example-co",
            campaign_name=campaign
        )
        
        # 1. Push task (should push to S3)
        task_id = q.push(task) # This is now the domain 'example.com'
        
        # Check S3 upload was called for task.json
        from cocli.core.sharding import get_domain_shard
        shard = get_domain_shard(domain) # 'a3' for example.com
        
        s3_task_key = f"campaigns/{campaign}/queues/enrichment/pending/{shard}/{domain}/task.json"
        mock_s3.upload_file.assert_called_with(
            str(q._get_task_dir(task_id) / "task.json"),
            bucket,
            s3_task_key
        )
        
        # 2. Poll task (should attempt S3 conditional write)
        # Mock S3 Success (PutObject returns OK)
        mock_s3.put_object.return_value = {}
        
        tasks = q.poll(batch_size=1)
        assert len(tasks) == 1
        assert tasks[0].domain == domain
        
        # Check S3 put_object was called with IfNoneMatch='*'
        s3_lease_key = f"campaigns/{campaign}/queues/enrichment/pending/{shard}/{domain}/lease.json"
        mock_s3.put_object.assert_called()
        args, kwargs = mock_s3.put_object.call_args
        assert kwargs['Key'] == s3_lease_key
        assert kwargs['IfNoneMatch'] == '*'

def test_s3_conditional_lease_collision(tmp_path, mock_s3):
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test_s3_campaign"
        bucket = "test-bucket"
        
        q = FilesystemEnrichmentQueue(campaign, s3_client=mock_s3, bucket_name=bucket)
        
        # Push a task locally
        task = QueueMessage(domain="test.com", company_slug="test", campaign_name=campaign)
        q.push(task)
        
        # Mock S3 Collision (412 Precondition Failed)
        from botocore.exceptions import ClientError
        error_response = {'Error': {'Code': 'PreconditionFailed', 'Message': 'At least one of the pre-conditions you specified did not hold'}}
        mock_s3.put_object.side_effect = ClientError(error_response, 'PutObject')
        
        # Mock GetObject to return a non-stale lease
        lease_data = {
            "worker_id": "other-worker",
            "created_at": datetime.now(UTC).isoformat(),
            "heartbeat_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
        }
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=MagicMock(return_value=json.dumps(lease_data).encode()))
        }
        
        tasks = q.poll(batch_size=1)
        assert len(tasks) == 0  # Should skip because lease is held by another

def test_s3_ack_immediate_cleanup(tmp_path, mock_s3):
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test_s3_campaign"
        bucket = "test-bucket"
        
        q = FilesystemEnrichmentQueue(campaign, s3_client=mock_s3, bucket_name=bucket)
        
        task_id = "test-task-id"
        # Setup local task dir
        task_dir = q._get_task_dir(task_id)
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text("{}")
        
        q.ack(task_id)
        
        # Verify S3 delete_objects was called
        mock_s3.delete_objects.assert_called_once()
        args, kwargs = mock_s3.delete_objects.call_args
        assert kwargs['Bucket'] == bucket
        keys = [obj['Key'] for obj in kwargs['Delete']['Objects']]
        assert any("task.json" in k for k in keys)
        assert any("lease.json" in k for k in keys)
