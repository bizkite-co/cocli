import pytest
from cocli.application.search_service import get_fuzzy_search_results
from cocli.core.text_utils import slugify
from cocli.core.paths import paths

@pytest.fixture
def populated_env(mock_cocli_env, mocker):
    """
    Extends mock_cocli_env by populating it with test data.
    """
    companies_dir = paths.companies
    
    # Create test companies
    companies = [
        {"name": "BizKite", "domain": "bizkite.com", "tags": ["tech", "startup", "test/default"]},
        {"name": "Flooring Experts", "domain": "floors.com", "tags": ["service", "home", "test/default"]},
        {"name": "Tech Solutions", "domain": "techsol.com", "tags": ["tech", "consulting", "test/default"]}
    ]

    for comp in companies:
        slug = slugify(comp["name"])
        comp_dir = companies_dir / slug
        comp_dir.mkdir(parents=True, exist_ok=True)
        index_path = comp_dir / "_index.md"
        index_path.write_text(f'''---
name: {comp["name"]}
domain: {comp["domain"]}
tags: {comp["tags"]}
---
''')
        tags_path = comp_dir / "tags.lst"
        tags_path.write_text("\n".join(comp["tags"]) + "\n")

    # Patch ExclusionManager to avoid real FS issues in tests
    mocker.patch('cocli.application.search_service.ExclusionManager.list_exclusions', return_value=[])

    # Build cache for the default 'test/default' campaign
    from cocli.core.cache import build_cache
    build_cache(campaign='test/default')

    return mock_cocli_env

def test_get_fuzzy_search_results_basic(populated_env):
    """Test basic search functionality."""
    # Search for "Biz"
    results = get_fuzzy_search_results(search_query="Biz", campaign_name="test/default")
    assert len(results) == 1
    assert results[0].name == "BizKite"

    # Search for "tech"
    results = get_fuzzy_search_results(search_query="tech", campaign_name="test/default")
    assert len(results) >= 2
    names = [r.name for r in results]
    assert "BizKite" in names
    assert "Tech Solutions" in names

def test_get_fuzzy_search_results_by_tag(populated_env):
    """Test searching explicitly by tag content."""
    # Search for "startup" tag
    results = get_fuzzy_search_results(search_query="startup", campaign_name="test/default")
    assert len(results) == 1
    assert results[0].name == "BizKite"

    # Search for "consulting" tag
    results = get_fuzzy_search_results(search_query="consulting", campaign_name="test/default")
    assert len(results) == 1
    assert results[0].name == "Tech Solutions"

def test_get_fuzzy_search_results_item_type(populated_env):
    """Test filtering by item type."""
    results = get_fuzzy_search_results(item_type="company", campaign_name="test/default")
    assert len(results) == 3
    
    results = get_fuzzy_search_results(item_type="person", campaign_name="test/default")
    assert len(results) == 0

def test_get_fuzzy_search_results_exclusions(populated_env, mocker):
    """Test that excluded items are filtered out."""
    from cocli.models.exclusion import Exclusion
    
    # Mock ExclusionManager to return one excluded company
    mock_exclusion = Exclusion(domain="bizkite.com", company_slug="bizkite", campaign="test/default")
    mocker.patch('cocli.application.search_service.ExclusionManager.list_exclusions', return_value=[mock_exclusion])

    results = get_fuzzy_search_results(search_query="Biz", campaign_name="test/default")
    # BizKite should be filtered out
    assert len(results) == 0

    results = get_fuzzy_search_results(search_query="tech", campaign_name="test/default")
    # Tech Solutions should still be there
    assert any(r.name == "Tech Solutions" for r in results)
    assert not any(r.name == "BizKite" for r in results)

def test_duckdb_query_error_handling(populated_env, mocker):
    """Test that search service handles DuckDB errors gracefully."""
    # Mock DuckDB execute to raise an error
    mocker.patch('duckdb.connect').side_effect = Exception("DuckDB connection error")
    
    results = get_fuzzy_search_results(search_query="anything", campaign_name="test/default")
    # Should return empty list instead of crashing
    assert results == []

def test_get_fuzzy_search_results_namespaced_campaign(mock_cocli_env, mocker):
    """Test searching within a namespaced campaign (e.g. test/sub/campaign)."""
    # Create test data in a namespaced directory
    namespaced_campaign = "test/sub/nested-campaign"
    campaign_dir = paths.campaign(namespaced_campaign)
    campaign_dir.mkdir(parents=True, exist_ok=True)
    
    # We need some companies to search. Build a custom populated set for this namespace.
    companies_dir = paths.companies
    comp_name = "Nested Biz"
    slug = slugify(comp_name)
    comp_dir = companies_dir / slug
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / "_index.md").write_text(f"---\nname: {comp_name}\ntags: [test, {namespaced_campaign}]\n---")
    
    # Build cache for this specific namespaced campaign
    from cocli.core.cache import build_cache
    build_cache(campaign=namespaced_campaign)
    
    results = get_fuzzy_search_results(search_query="Nested", campaign_name=namespaced_campaign)
    assert len(results) == 1
    assert results[0].name == comp_name
    
    # Verify the cache file was actually created with a sanitized name
    from cocli.core.cache import get_cache_path
    cache_file = get_cache_path(campaign=namespaced_campaign)
    assert cache_file.name == "fz_cache_test_sub_nested-campaign.json"
    assert cache_file.exists()


