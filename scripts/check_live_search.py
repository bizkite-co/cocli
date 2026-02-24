# POLICY: frictionless-data-policy-enforcement
import logging
import sys
from cocli.application.search_service import get_fuzzy_search_results
from cocli.core.config import set_campaign

# Setup minimal logging to stdout
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

def test_search() -> None:
    campaign = "roadmap"
    set_campaign(campaign)
    print(f"--- Testing Search for Campaign: {campaign} ---")
    
    # 1. Test All Leads (Empty query)
    results = get_fuzzy_search_results("", item_type="company", campaign_name=campaign)
    print(f"All Leads Count: {len(results)}")
    if results:
        print(f"First result: {results[0].name} ({results[0].slug})")
    else:
        print("NO RESULTS FOUND FOR 'ALL LEADS'")

    # 2. Test specific query
    results = get_fuzzy_search_results("Auctus", campaign_name=campaign)
    print(f"Search 'Auctus' Count: {len(results)}")

if __name__ == "__main__":
    test_search()
