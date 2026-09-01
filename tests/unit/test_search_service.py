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
        (comp_dir / "_index.md").write_text(
            f"---\nname: {item['name']}\ntags:\n{tags_str}\n---"
        )

    # Build the USV cache for the test campaign
    build_cache(campaign="test/default")
    return mock_cocli_env


def test_cache_valid_after_build(populated_env):
    """CompanyCacheItem is 10 columns; stale expected=8 would rebuild forever."""
    from cocli.core.cache import is_cache_valid

    assert is_cache_valid(campaign="test/default") is True


def test_get_fuzzy_search_results_basic(populated_env):
    """Test basic search functionality."""
    results = get_fuzzy_search_results(search_query="Biz", campaign_name="test/default")
    assert len(results) == 1
    assert results[0].name == "BizKite"


def test_quoted_checkpoint_name_stripped_in_search(mock_cocli_env, mocker):
    """All Leads prefers checkpoint name over cache; quote policy must apply."""
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    import cocli.application.search_service as search_service

    search_service._con = None
    search_service._last_campaign = None

    campaign = "test/quotes"
    mocker.patch("cocli.core.config.get_campaign", return_value=campaign)
    mocker.patch("cocli.application.search_service.get_campaign", return_value=campaign)

    slug = "n1-hardwood-flooring"
    prospect_idx = paths.campaign(campaign).index("google_maps_prospects")
    prospect_idx.path.mkdir(parents=True, exist_ok=True)
    prospect = GoogleMapsProspect.model_validate(
        {
            "place_id": "ChIJhardwoodflooringaaa",
            "company_slug": slug,
            "name": "# 1 Hardwood Flooring",
        }
    )
    # Write the raw scraper-artifact form that bypasses Pydantic on disk.
    dirty = prospect.to_usv().replace(
        "# 1 Hardwood Flooring", '"""# 1 Hardwood Flooring"""'
    )
    prospect_idx.checkpoint.write_text(dirty, encoding="utf-8")
    GoogleMapsProspect.write_datapackage(campaign)

    comp_dir = paths.companies / slug
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / "_index.md").write_text(
        f"---\nname: Other Name\ntags:\n  - {campaign}\n---\n"
    )
    build_cache(campaign=campaign)

    results = get_fuzzy_search_results(
        search_query="Hardwood",
        campaign_name=campaign,
        force_rebuild_cache=True,
    )
    assert len(results) == 1
    assert str(results[0].name) == "# 1 Hardwood Flooring"
    assert '"' not in str(results[0].name)


def test_get_fuzzy_search_results_by_tag(populated_env):
    """Test searching explicitly by tag content."""
    results = get_fuzzy_search_results(
        search_query="startup", campaign_name="test/default"
    )
    assert len(results) == 1
    assert results[0].name == "BizKite"


def test_get_fuzzy_search_results_item_type(populated_env):
    """Test filtering by item type."""
    results = get_fuzzy_search_results(
        item_type="company", campaign_name="test/default"
    )
    assert len(results) == 3


def test_get_fuzzy_search_results_exclusions(populated_env, mocker):
    """Test that excluded items are filtered out."""
    from cocli.models.campaigns.indexes.exclusion import Exclusion

    # Mock list_all_exclusions (campaign + shared/global, combined) to
    # return one excluded company
    mock_exclusion = Exclusion(
        domain=None, company_slug="bizkite", campaign="test/default"
    )
    mocker.patch(
        "cocli.application.search_service.list_all_exclusions",
        return_value=[mock_exclusion],
    )

    results = get_fuzzy_search_results(search_query="Biz", campaign_name="test/default")
    assert len(results) == 0

    results = get_fuzzy_search_results(
        search_query="tech", campaign_name="test/default"
    )
    assert any(r.name == "Tech Solutions" for r in results)


def test_get_fuzzy_search_results_namespaced_campaign(mock_cocli_env):
    """Test searching within a namespaced campaign."""
    namespaced_campaign = "test/sub/nested-campaign"

    # Create test data
    comp_name = "Nested Biz"
    slug = slugify(comp_name)
    comp_dir = paths.companies / slug
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / "_index.md").write_text(
        f"---\nname: {comp_name}\ntags: [test, {namespaced_campaign}]\n---"
    )

    # Build cache for this namespace
    build_cache(campaign=namespaced_campaign)

    results = get_fuzzy_search_results(
        search_query="Nested", campaign_name=namespaced_campaign
    )
    assert len(results) == 1
    assert results[0].name == comp_name
