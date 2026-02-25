# POLICY: frictionless-data-policy-enforcement
import logging
import sys
from cocli.application.search_service import get_fuzzy_search_results
from cocli.core.config import set_campaign

# Setup minimal logging to stdout
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

def test_search() -> None:
    # Use the current campaign
    from cocli.core.config import get_campaign
    campaign = get_campaign() or "roadmap"
    set_campaign(campaign)
    print(f"--- Testing Search for Campaign: {campaign} ---")
    
    # 1. Test All Leads (Empty query)
    results = get_fuzzy_search_results("", item_type="company", campaign_name=campaign)
    print(f"All Leads Count: {len(results)}")
    if results:
        print(f"First result: {results[0].name} ({results[0].slug})")
    else:
        print("NO RESULTS FOUND FOR 'ALL LEADS'")

    # 2. Test 'To Call' specific
    print("\n--- Testing 'To Call' template ---")
    results = get_fuzzy_search_results("", filters={"to_call": True}, campaign_name=campaign)
    print(f"To Call Count: {len(results)}")
    for res in results:
        print(f"  - {res.name} ({res.slug})")

if __name__ == "__main__":
    test_search()
