# POLICY: frictionless-data-policy-enforcement
import pytest
from cocli.application.search_service import get_fuzzy_search_results, get_template_counts
from cocli.core.config import set_campaign
from cocli.core.paths import paths
from cocli.models.campaigns.queues.to_call import ToCallTask

@pytest.fixture
def mock_to_call_env(tmp_path, monkeypatch):
    """Sets up a controlled environment with specific to-call tasks."""
    # 1. Setup mock data home
    data_home = tmp_path / "cocli_data"
    data_home.mkdir()
    
    # FDPE: Explicitly re-root the global paths authority using the new setter.
    # This prevents 'test-sync' from being created in the user's real data home.
    monkeypatch.setattr(paths, "root", data_home)
    
    campaign = "test-sync"
    set_campaign(campaign)
    
    # 2. Create a company
    slug = "test-company-1"
    company_dir = data_home / "companies" / slug
    company_dir.mkdir(parents=True)
    index_md = company_dir / "_index.md"
    # CRITICAL: It MUST have the campaign name in tags to be included in the campaign cache
    index_md.write_text("name: Test Company 1\ndomain: test1.com\ntags: [test-sync]\n", encoding="utf-8")
    
    # 3. Create a to-call task marker
    task = ToCallTask(
        company_slug=slug,
        domain="test1.com",
        campaign_name=campaign,
        ack_token=None
    )
    task.save()
    
    # 4. Verify path exists
    task_path = task.get_local_path()
    assert task_path.exists(), f"Task path should exist at {task_path}"
    # Verify it is actually inside our temp dir
    assert str(data_home.resolve()) in str(task_path.resolve()), f"LEAKAGE DETECTED: Task path {task_path} is not in {data_home}"
    
    return campaign, slug

def test_to_call_duckdb_integration(mock_to_call_env):
    """
    Step-by-step verification of the To-Call DuckDB pipeline.
    """
    campaign, slug = mock_to_call_env
    
    # Step 1: Trigger Search (Warms DuckDB)
    get_fuzzy_search_results("", item_type="company", campaign_name=campaign, force_rebuild_cache=True)
    
    from cocli.application.search_service import _con
    assert _con is not None, "DuckDB connection should be initialized"
    
    # Step 2: Check search cache table (items_cache)
    cache_rows = _con.execute("SELECT slug FROM items_cache").fetchall()
    assert any(r[0] == slug for r in cache_rows), f"Slug '{slug}' must exist in items_cache"

    # Step 3: Check items_to_call table
    to_call_rows = _con.execute("SELECT * FROM items_to_call").fetchall()
    assert len(to_call_rows) == 1, "Should have 1 task in items_to_call table"
    assert to_call_rows[0][0] == slug, f"Slug in table '{to_call_rows[0][0]}' should match '{slug}'"
    
    # Step 4: Check JOIN view (items)
    view_rows = _con.execute("SELECT slug, is_to_call FROM items WHERE slug = ?", [slug]).fetchone()
    assert view_rows is not None, "Company should exist in unified 'items' view"
    assert view_rows[1] is True, f"Company {slug} should have is_to_call = True in view"
    
    # Step 5: Verify Template Filter
    to_call_results = get_fuzzy_search_results("", filters={"to_call": True}, campaign_name=campaign)
    assert len(to_call_results) == 1, "Template filter should return 1 result"
    assert to_call_results[0].slug == slug
    
    # Step 6: Verify Template Counts
    counts = get_template_counts(campaign_name=campaign)
    assert counts.get("tpl_to_call") == 1, f"Template count for 'tpl_to_call' should be 1, got {counts.get('tpl_to_call')}"

def test_to_call_removal_sync(mock_to_call_env):
    """Verify that removing the file updates DuckDB immediately."""
    campaign, slug = mock_to_call_env
    
    # Warm it
    get_fuzzy_search_results("", campaign_name=campaign, force_rebuild_cache=True)
    
    # Delete the task file
    task = ToCallTask(company_slug=slug, domain="test1.com", campaign_name=campaign, ack_token=None)
    task_path = task.get_local_path()
    task_path.unlink()
    
    # Trigger search again (DuckDB should re-scan because mtime of pending dir changed)
    results = get_fuzzy_search_results("", filters={"to_call": True}, campaign_name=campaign)
    
    assert len(results) == 0, "Company should disappear from To-Call results after file deletion"
    
    counts = get_template_counts(campaign_name=campaign)
    assert counts.get("tpl_to_call") == 0, "Count should update to 0"
