# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
from typing import List, Dict, Any
from cocli.application.search_service import get_fuzzy_search_results
from cocli.models.companies.company import Company
from cocli.core.config import set_campaign

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("to_call")

async def populate_to_call(campaign_name: str, limit: int = 50):
    set_campaign(campaign_name)
    logger.info(f"--- Populating To-Call for {campaign_name} (Limit: {limit}) ---")
    
    # 1. Identify Top Leads via optimized search service
    # The search service already uses the compacted index we just cleaned.
    filters = {"has_contact_info": True}
    results = get_fuzzy_search_results(
        "", 
        item_type="company", 
        campaign_name=campaign_name,
        filters=filters,
        limit=500 # Scan top 500 to find best 50
    )
    
    # Sort by Rating * Reviews Count descending
    top_prospects = sorted(
        results, 
        key=lambda x: (x.average_rating or 0) * (x.reviews_count or 0), 
        reverse=True
    )
    
    logger.info(f"Identified {len(top_prospects)} candidates with contact info.")
    for p in top_prospects[:5]:
        logger.info(f"  [CANDIDATE] {p.slug} | Rating: {p.average_rating} | Reviews: {p.reviews_count}")
    
    # 2. Tag and Hydrate
    tagged = 0
    for p in top_prospects:
        if tagged >= limit:
            break
            
        if p.slug:
            company = Company.get(p.slug)
            if company:
                # Update metadata if missing
                changed = False
                if p.average_rating and not company.average_rating:
                    company.average_rating = p.average_rating
                    changed = True
                if p.reviews_count and not company.reviews_count:
                    company.reviews_count = p.reviews_count
                    changed = True
                
                if "to-call" not in company.tags:
                    # toggle_to_call handles both tag and queue USV
                    company.toggle_to_call()
                    tagged += 1
                    logger.info(f"  [TAGGED] {p.slug} (Rating: {p.average_rating}, Reviews: {p.reviews_count})")
                elif changed:
                    company.save()
                    
    logger.info(f"--- Finished. Newly tagged: {tagged} ---")

if __name__ == "__main__":
    asyncio.run(populate_to_call("roadmap", limit=50))
