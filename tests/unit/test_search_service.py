import pytest
from slugify import slugify

from cocli.application.search_service import get_fuzzy_search_results
from cocli.core.paths import paths
from cocli.core.cache import build_cache

@pytest.fixture
def populated_env(mock_cocli_env):
    """Populates the mock environment with test companies."""
    companies_dir = paths.companies
    
    test_data = [
        {"name": "BizKite", "tags": ["startup", "test/default"]},
        {"name": "Tech Solutions", "tags": ["it", "test/default"]},
        {"name": "Green Energy", "tags": ["solar", "test/default"]},
    ]
    
    for item in test_data:
        slug = slugify(item["name"])
        comp_dir = companies_dir / slug
        comp_dir.mkdir(parents=True, exist_ok=True)
        tags_str = "\n".join([f"  - {t}" for t in item["tags"]])
        (comp_dir / "_index.md").write_text(f"---\nname: {item['name']}\ntags:\n{tags_str}\n---")
        
    # Build the USV cache for the test campaign
    build_cache(campaign="test/default")
    return mock_cocli_env

def test_get_fuzzy_search_results_basic(populated_env):
    """Test basic search functionality."""
    results = get_fuzzy_search_results(search_query="Biz", campaign_name="test/default")
    assert len(results) == 1
    assert results[0].name == "BizKite"

def test_get_fuzzy_search_results_by_tag(populated_env):
    """Test searching explicitly by tag content."""
    results = get_fuzzy_search_results(search_query="startup", campaign_name="test/default")
    assert len(results) == 1
    assert results[0].name == "BizKite"

def test_get_fuzzy_search_results_item_type(populated_env):
    """Test filtering by item type."""
    results = get_fuzzy_search_results(item_type="company", campaign_name="test/default")
    assert len(results) == 3

def test_get_fuzzy_search_results_exclusions(populated_env, mocker):
    """Test that excluded items are filtered out."""
    from cocli.models.exclusion import Exclusion
    
    # Mock ExclusionManager to return one excluded company
    mock_exclusion = Exclusion(domain=None, company_slug="bizkite", campaign="test/default")
    mocker.patch('cocli.application.search_service.ExclusionManager.list_exclusions', return_value=[mock_exclusion])
    
    results = get_fuzzy_search_results(search_query="Biz", campaign_name="test/default")
    assert len(results) == 0
    
    results = get_fuzzy_search_results(search_query="tech", campaign_name="test/default")
    assert any(r.name == "Tech Solutions" for r in results)

def test_get_fuzzy_search_results_namespaced_campaign(mock_cocli_env):
    """Test searching within a namespaced campaign."""
    namespaced_campaign = "test/sub/nested-campaign"
    
    # Create test data
    comp_name = "Nested Biz"
    slug = slugify(comp_name)
    comp_dir = paths.companies / slug
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / "_index.md").write_text(f"---\nname: {comp_name}\ntags: [test, {namespaced_campaign}]\n---")
    
    # Build cache for this namespace
    build_cache(campaign=namespaced_campaign)
    
    results = get_fuzzy_search_results(search_query="Nested", campaign_name=namespaced_campaign)
    assert len(results) == 1
    assert results[0].name == comp_name
