import pytest
from datetime import datetime
from unittest.mock import MagicMock
from cocli.core.domain_index_manager import DomainIndexManager
from cocli.models.campaign import Campaign
from cocli.models.website_domain_csv import WebsiteDomainCsv

@pytest.fixture
def s3_manager():
    # Load roadmap campaign for testing against real bucket (if creds available)
    campaign = Campaign.load("roadmap")
    return DomainIndexManager(campaign)

def test_s3_round_trip(s3_manager):
    test_domain = "test-atomic-index.com"
    item = WebsiteDomainCsv(
        domain=test_domain,
        company_name="Test USV Inc",
        ip_address="127.0.0.1"
    )
    
    # 1. Add (performs CAS write and manifest swap)
    s3_manager.add_or_update(item)
    
    # 2. Get by domain (verifies real-time visibility from Inbox)
    retrieved = s3_manager.get_by_domain(test_domain)
    assert retrieved is not None
    assert retrieved.domain == test_domain
    assert retrieved.company_name == "Test USV Inc"

def test_duckdb_query(s3_manager):
    # Setup some dummy data in inbox
    item = WebsiteDomainCsv(
        domain="duckdb-test.com",
        company_name="DuckDB Test Corp",
        updated_at=datetime.utcnow()
    )
    s3_manager.add_or_update(item)
    
    # Query via DuckDB
    results = s3_manager.query("company_name = 'DuckDB Test Corp'")
    assert len(results) >= 1
    assert any(r.domain == "duckdb-test.com" for r in results)

def test_local_round_trip(tmp_path, monkeypatch):
    """Verifies that DomainIndexManager works with local filesystem."""
    monkeypatch.setenv("COCLI_DATA_HOME", str(tmp_path))
    
    mock_camp = MagicMock()
    mock_camp.name = "local-test"
    
    manager = DomainIndexManager(campaign=mock_camp)
    
    # Ensure directories exist
    (tmp_path / "indexes" / "domains").mkdir(parents=True, exist_ok=True)
    
    # 1. Add item
    item = WebsiteDomainCsv(
        domain="local-test.com",
        company_name="Local Success",
        updated_at=datetime.utcnow()
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
        updated_at=datetime.utcnow()
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
    
    # 7. Check if manifest exists
    manifest = manager.get_latest_manifest()
    assert "local-test.com" in manifest.shards
    assert manifest.shards["local-test.com"].path.startswith("indexes/shards/")