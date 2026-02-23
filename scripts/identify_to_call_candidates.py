# POLICY: frictionless-data-policy-enforcement
import logging
from typing import List
from cocli.models.companies.company import Company
from cocli.core.config import set_campaign

logger = logging.getLogger(__name__)

def identify_candidates() -> None:
    # Ensure we are in turboship context for filtering if needed
    set_campaign("turboship")
    
    prime_categories = ["insurance broker", "wealth manager", "financial planner"]
    must_have_keyword = "retirement"
    
    candidates: List[Company] = []
    
    print("Scanning companies for prime candidates...")
    
    count = 0
    for company in Company.get_all():
        count += 1
        if count % 500 == 0:
            print(f"Processed {count} companies...")
            
        # 1. Must be enriched (has phone and email ideally)
        if not company.phone_number and not company.phone_1:
            continue
            
        # 2. Match Niche
        cat_match = any(pc in [c.lower() for c in company.categories] for pc in prime_categories)
        kw_match = must_have_keyword in [k.lower() for k in company.keywords] or must_have_keyword in (company.description or "").lower()
        
        if cat_match and kw_match:
            candidates.append(company)
            print(f"FOUND: {company.name} ({company.slug})")
            if len(candidates) >= 10:
                break
                
    if len(candidates) < 10:
        print("Relaxing constraints to find more candidates...")
        # Relax constraints if needed (e.g. just categories)
        for company in Company.get_all():
            if company in candidates:
                continue
            cat_match = any(pc in [c.lower() for c in company.categories] for pc in prime_categories)
            if cat_match:
                candidates.append(company)
                print(f"FOUND (relaxed): {company.name} ({company.slug})")
                if len(candidates) >= 10:
                    break

    print(f"\nSelected {len(candidates)} candidates for the To-Call queue:")
    for c in candidates:
        print(f"- {c.name} ({c.slug}) | Phone: {c.phone_number or c.phone_1}")
        # Add the tag
        if "to-call" not in c.tags:
            c.tags.append("to-call")
            c.save()
            print("  [Tagged as to-call]")

if __name__ == "__main__":
    identify_candidates()
