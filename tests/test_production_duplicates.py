# POLICY: frictionless-data-policy-enforcement
import pytest
import logging
from cocli.application.services import ServiceContainer
from cocli.core.config import set_campaign

# Disable noise during production data load
logging.getLogger("cocli").setLevel(logging.WARNING)

@pytest.mark.use_prod_data
def test_no_duplicates_in_all_leads_roadmap():
    """
    Reproduction test: Fails if 'All Leads' fuzzy search returns duplicate companies.
    Uses actual production data for the 'roadmap' campaign.
    """
    campaign = "roadmap"
    set_campaign(campaign)
    
    services = ServiceContainer(campaign_name=campaign)
    
    # Simulate 'All Leads' template logic from CompanyList.apply_template
    # tpl_all: filter_contact=False, sort_recent=True
    search_filters = {}
    sort_by = "recent"
    
    # We want a large enough limit to catch duplicates
    limit = 1000
    
    results = services.fuzzy_search(
        search_query="",
        item_type="company",
        filters=search_filters,
        sort_by=sort_by,
        limit=limit,
        offset=0
    )
    
    if not results:
        # If we are in a CI/Minimal environment where PROD data isn't synced, skip instead of fail
        from cocli.core.paths import paths
        checkpoint = paths.campaign(campaign).index("google_maps_prospects").checkpoint
        if not checkpoint.exists():
            pytest.skip(f"Production data not found at {checkpoint}. Skipping production duplication check.")
        else:
            pytest.fail(f"No results returned for {campaign} even though checkpoint exists at {checkpoint}")
    
    slugs = [r.slug for r in results if r.slug]
    
    # Identify duplicates
    duplicates = {}
    seen = set()
    for slug in slugs:
        if slug in seen:
            duplicates[slug] = duplicates.get(slug, 1) + 1
        seen.add(slug)
            
    if duplicates:
        msg = f"Found {len(duplicates)} duplicate slugs in 'All Leads' search results:\n"
        # Show top 10 duplicates
        sorted_dupes = sorted(duplicates.items(), key=lambda x: x[1], reverse=True)
        for slug, count in sorted_dupes[:10]:
            msg += f"  - {slug}: {count} occurrences\n"
        pytest.fail(msg)

if __name__ == "__main__":
    test_no_duplicates_in_all_leads_roadmap()
