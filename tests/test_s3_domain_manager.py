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
    
    # 1. Add
    s3_manager.add_or_update(item)
    
    # 2. Get
    fetched = s3_manager.get_by_domain(test_domain)
    assert fetched is not None
    assert str(fetched.domain) == test_domain
    assert fetched.company_name == "Test USV Inc"
    assert fetched.ip_address == "127.0.0.1"
    
    # 3. Cleanup
    s3_manager.s3_client.delete_object(
        Bucket=s3_manager.s3_bucket_name,
        Key=s3_manager._get_s3_key(test_domain)
    )

def test_duckdb_query(s3_manager):
    # This assumes some .usv files exist in the roadmap bucket
    results = s3_manager.query("domain = 'apple.com'")
    # We don't assert length since apple.com might not be there, 
    # but we ensure the query doesn't crash
    assert isinstance(results, list)
