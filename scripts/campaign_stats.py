import sys
import glob
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.paths import paths
from cocli.core.config import get_campaign

def run_stats(campaign_name: str) -> None:
    print(f"================ Campaign Stats: {campaign_name} ================")
    
    # 1. GM-List Pending / Completed Tasks
    gm_list_dir = paths.queue(campaign_name, "gm-list")
    completed_tasks = len(list(gm_list_dir.completed.glob("**/*.json")))
    pending_tasks = len(list(gm_list_dir.pending.glob("**/*.json")))
    
    print(f"GM-List Queue Status:")
    print(f"  Completed Tasks: {completed_tasks}")
    print(f"  Pending Leases:  {pending_tasks}")
    
    # 2. Scraped Lead Stats
    results_dir = gm_list_dir.completed / "results"
    usv_files = glob.glob(str(results_dir / "**/*.usv"), recursive=True)
    
    unique_place_ids = set()
    leads_with_domain = set()
    total_records = 0
    
    for f_path in usv_files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    parts = line.split("\x1f")
                    if parts:
                        place_id = parts[0]
                        unique_place_ids.add(place_id)
                        total_records += 1
                        # The domain is at index 5 in GoogleMapsListItem fields:
                        # place_id, company_slug, name, category, phone, domain
                        if len(parts) > 5 and parts[5].strip():
                            leads_with_domain.add(place_id)
        except Exception:
            pass
            
    print(f"\nLead Scraping Results:")
    print(f"  Total Scraped Records: {total_records}")
    print(f"  Unique Leads Scraped:  {len(unique_place_ids)}")
    if len(unique_place_ids) > 0:
        print(f"  Leads with Websites:   {len(leads_with_domain)} ({len(leads_with_domain) / len(unique_place_ids) * 100:.1f}%)")
    else:
        print(f"  Leads with Websites:   0")
        
    # 3. Enrichment Queue Stats
    enrich_dir = paths.queue(campaign_name, "enrichment")
    completed_enrich = len(list(enrich_dir.completed.glob("**/*.json")))
    pending_enrich = len(list(enrich_dir.pending.glob("**/*.json")))
    print(f"\nEnrichment Queue Status:")
    print(f"  Completed: {completed_enrich}")
    print(f"  Pending:   {pending_enrich}")
    print("=================================================================")

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else get_campaign()
    if not campaign:
        print("ERROR: Please specify campaign name or set a default campaign.")
        sys.exit(1)
    run_stats(campaign)
