import pytest
from cocli.core.s3_domain_manager import S3DomainManager
from cocli.models.campaign import Campaign
from cocli.models.website_domain_csv import WebsiteDomainCsv

@pytest.fixture
def s3_manager():
    # Load roadmap campaign for testing against real bucket (if creds available)
    campaign = Campaign.load("roadmap")
    return S3DomainManager(campaign)

def test_s3_round_trip(s3_manager):
    test_domain = "test-atomic-index.com"
    item = WebsiteDomainCsv(
        domain=test_domain,
        company_name="Test USV Inc",
        ip_address="127.0.0.1"
    )
    
    # 1. Add (performs CAS write and manifest swap)
    s3_manager.add_or_update(item)
    
    # 2. Get (via manifest)
    fetched = s3_manager.get_by_domain(test_domain)
    assert fetched is not None
    assert str(fetched.domain) == test_domain
    assert fetched.company_name == "Test USV Inc"
    assert fetched.ip_address == "127.0.0.1"
    
    # 3. Verify manifest exists and is current
    manifest = s3_manager.get_latest_manifest()
    assert test_domain in manifest.shards
    shard = manifest.shards[test_domain]
    assert shard.path.startswith(s3_manager.shards_prefix)

def test_duckdb_query(s3_manager):
    # This uses the manifest-driven DuckDB query
    results = s3_manager.query("domain = 'test-atomic-index.com'")
    assert isinstance(results, list)
    if results:
        assert results[0].domain == 'test-atomic-index.com'