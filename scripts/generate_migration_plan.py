import os
import sys
from pathlib import Path
from cocli.core.config import get_campaign_dir

def generate_plan(campaign_name: str):
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        print(f"Error: Campaign {campaign_name} not found.")
        return

    prospect_dir = campaign_dir / "indexes" / "google_maps_prospects"
    plan_path = campaign_dir / "migration_plan.txt"
    
    # 1. Find all candidate USV files
    search_paths = [prospect_dir, prospect_dir / "inbox"]
    candidates = []
    
    for base_path in search_paths:
        if not base_path.exists():
            continue
        for file_path in base_path.glob("*.usv"):
            # Skip if it's already in a shard directory
            if file_path.parent.name in "0123456789abcdef-":
                continue
            candidates.append(str(file_path))
    
    # 2. Write the plan
    with open(plan_path, 'w') as f:
        for c in sorted(candidates):
            f.write(f"{c}\n")
            
    print(f"Plan generated: {len(candidates)} files to migrate.")
    print(f"Plan location: {plan_path}")

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    generate_plan(campaign)