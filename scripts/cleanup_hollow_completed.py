#!/usr/bin/env python3
import os
import shutil
import glob
from pathlib import Path

def cleanup():
    campaign = "roadmap"
    base_dir = Path("/home/mstouffer/.local/share/cocli_data/campaigns") / campaign
    completed_dir = base_dir / "queues" / "gm-details" / "completed"
    recovery_dir = base_dir / "recovery" / "completed"
    
    # 1. Ensure recovery dir exists
    recovery_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Scanning {completed_dir}...")
    all_files = glob.glob(str(completed_dir / "*.json"))
    total_found = len(all_files)
    
    hollow_count = 0
    valid_count = 0
    
    import json
    for f_path in all_files:
        try:
            with open(f_path, 'r') as f:
                data = json.load(f)
            
            name = data.get("name", "")
            slug = data.get("company_slug", "")
            
            # Criteria for "Hollow": name or slug < 3 chars
            if not name or not slug or len(name) < 3 or len(slug) < 3:
                shutil.move(f_path, recovery_dir / os.path.basename(f_path))
                hollow_count += 1
            else:
                valid_count += 1
        except Exception as e:
            print(f"Error processing {f_path}: {e}")

    print("-" * 40)
    print(f"Total processed: {total_found}")
    print(f"Moved to recovery (Hollow): {hollow_count}")
    print(f"Remaining in completed (Valid): {valid_count}")

if __name__ == "__main__":
    cleanup()
