from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv

def test_usv_serialization():
    # 1. Test basic round-trip
    item = WebsiteDomainCsv(
        domain="example.com",
        company_name="Apple, Inc.", # Testing internal comma
        tags=["tech", "fruit"],
        ip_address="1.2.3.4"
    )
    
    usv = item.to_usv()
    
    # Verify delimiter count (N-1)
    fields_count = len(WebsiteDomainCsv.model_fields)
    assert usv.count('\x1f') == fields_count - 1
    
    rebuilt = WebsiteDomainCsv.from_usv(usv)
    assert str(rebuilt.domain) == "example.com"
    assert rebuilt.company_name == "Apple, Inc."
    assert "tech" in rebuilt.tags
    assert rebuilt.ip_address == "1.2.3.4"

def test_usv_schema_drift():
    # 2. Test Schema Drift (Simulation)
    # Create a truncated USV string (missing trailing fields like updated_at)
    legacy_usv = "\x1f".join(["legacy.com", "Legacy Co"])
    rebuilt_legacy = WebsiteDomainCsv.from_usv(legacy_usv)
    assert str(rebuilt_legacy.domain) == "legacy.com"
    assert rebuilt_legacy.company_name == "Legacy Co"
    assert rebuilt_legacy.updated_at is not None # Default factory or default logic
