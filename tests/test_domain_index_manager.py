import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch
from cocli.core.domain_index_manager import DomainIndexManager
from cocli.models.website_domain_csv import WebsiteDomainCsv

@pytest.fixture
def mock_s3_manager():
    """Mocked DomainIndexManager for S3 tests."""
    with patch("boto3.Session") as mock_session:
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        
        # Load a fake campaign
        campaign = MagicMock()
        campaign.name = "test-campaign"
        
        # Patch load_campaign_config to return mock data
        with patch("cocli.core.config.load_campaign_config") as mock_config:
            mock_config.return_value = {
                "aws": {"data_bucket_name": "test-bucket"}
            }
            manager = DomainIndexManager(campaign)
            manager.s3_client = mock_client
            return manager

def test_s3_round_trip(mock_s3_manager):
    test_domain = "test-atomic-index.com"
    item = WebsiteDomainCsv(
        domain=test_domain,
        company_name="Test USV Inc",
        ip_address="127.0.0.1"
    )
    
    # Mock _read_object for LATEST and Manifest
    mock_s3_manager._read_object = MagicMock(side_effect=[
        "indexes/domains/manifests/latest.usv", # LATEST pointer
        "", # Empty manifest content for bootstrap
    ])
    
    # 1. Add (performs write to sharded inbox)
    mock_s3_manager.add_or_update(item)
    
    # Verify s3 write call
    shard_id = mock_s3_manager.get_shard_id(test_domain)
    mock_s3_manager.s3_client.put_object.assert_called()
    call_args = mock_s3_manager.s3_client.put_object.call_args[1]
    assert call_args["Bucket"] == "test-bucket"
    assert f"indexes/domains/inbox/{shard_id}/" in call_args["Key"]

def test_duckdb_query(mock_s3_manager):
    # This test is harder to mock fully as it uses DuckDB to read from S3.
    # For now, let's just skip it if not in a real S3 environment,
    # or rely on the local round trip for logic verification.
    pytest.skip("Full DuckDB S3 query test requires live S3 or complex moto setup")

def test_local_round_trip(tmp_path, monkeypatch):
    """Verifies that DomainIndexManager works with local filesystem."""
    monkeypatch.setenv("COCLI_DATA_HOME", str(tmp_path))
    
    mock_camp = MagicMock()
    mock_camp.name = "local-test"
    
    manager = DomainIndexManager(campaign=mock_camp)
    # Force local mode for the test
    manager.is_cloud = False
    manager.protocol = ""
    manager.root_dir = tmp_path / "indexes"
    

    # 1. Add item
    item = WebsiteDomainCsv(
        domain="local-test.com",
        company_name="Local Success",
        updated_at=datetime.now(UTC)
    )
    manager.add_or_update(item)
    
    # 2. Query immediately (Read from Inbox)
    retrieved = manager.get_by_domain("local-test.com")
    assert retrieved is not None
    assert retrieved.domain == "local-test.com"
    assert retrieved.company_name == "Local Success"
    
    # 3. Add second item
    item2 = WebsiteDomainCsv(
        domain="local-test2.com",
        company_name="Pending Local",
        updated_at=datetime.now(UTC)
    )
    manager.add_or_update(item2)
    
    # 4. Query both
    all_items = manager.query()
    assert len(all_items) >= 2
    domains = [d.domain for d in all_items]
    assert "local-test.com" in domains
    assert "local-test2.com" in domains

    # 5. Compact Inbox
    manager.compact_inbox()
    
    # 6. Verify that it still works (now reading from Shard)
    final_items = manager.query()
    assert len(final_items) >= 2
    assert any(d.domain == "local-test.com" for d in final_items)
    
    # 7. Check if manifest exists and uses deterministic shard IDs
    manifest = manager.get_latest_manifest()

    shard_id = manager.get_shard_id("local-test.com")

    assert shard_id in manifest.shards
    assert manifest.shards[shard_id].path.startswith("indexes/domains/shards/")
