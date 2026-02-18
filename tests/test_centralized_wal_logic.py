import shutil
from pathlib import Path
from cocli.core.paths import paths
from cocli.core.wal import append_update, read_updates
import logging

logger = logging.getLogger(__name__)

def test_centralized_wal():
    # Setup temporary data root for testing
    test_root = Path("/tmp/cocli_test_wal")
    if test_root.exists():
        shutil.rmtree(test_root)
    test_root.mkdir(parents=True)
    
    # Override paths.root for the test
    paths.root = test_root
    
    company_slug = "test-company-123"
    company_dir = test_root / "companies" / company_slug
    company_dir.mkdir(parents=True)
    
    logger.debug(f"Testing WAL with root: {test_root}")
    
    # 1. Append an update
    append_update(company_dir, "phone_number", "555-0199")
    append_update(company_dir, "website_url", "https://test.com")
    
    # 2. Verify files exist in centralized WAL
    wal_dir = test_root / "wal"
    logger.debug(f"Checking WAL directory: {wal_dir}")
    usv_files = list(wal_dir.glob("*.usv"))
    logger.debug(f"Found {len(usv_files)} WAL files: {[f.name for f in usv_files]}")
    
    assert len(usv_files) == 1
    
    # 3. Read updates back
    records = read_updates(company_dir)
    logger.debug(f"Read {len(records)} records for {company_slug}:")
    for r in records:
        logger.debug(f"  - {r.field}: {r.value} (target={r.target})")
        
    assert len(records) == 2
    assert records[0].field == "phone_number"
    assert records[0].value == "555-0199"
    assert records[1].field == "website_url"
    assert records[1].value == "https://test.com"
    
    logger.info("SUCCESS: Centralized WAL is working correctly.")

if __name__ == "__main__":
    test_centralized_wal()
