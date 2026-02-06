#!/usr/bin/env python3
import os
import glob
import re
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.models.google_maps_prospect import GoogleMapsProspect

def compile_list():
    campaign = "roadmap"
    recovery_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/recovery")
    completed_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/queues/gm-details/completed")
    pending_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/queues/gm-details/pending")
    index_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/indexes/google_maps_prospects")
    
    # 1. Get already completed valid IDs (to exclude)
    completed_ids = set()
    if completed_dir.exists():
        for f in completed_dir.glob("*.json"):
            completed_ids.add(f.stem)
    print(f"Loaded {len(completed_ids)} already-completed valid IDs.")

    # 2. Get currently pending IDs (to avoid re-enqueuing)
    pending_ids = set()
    if pending_dir.exists():
        for f in pending_dir.glob("*/*/task.json"):
            pending_ids.add(f.parent.name)
    print(f"Loaded {len(pending_ids)} currently pending IDs.")

    # 3. Extract PIDs from all recovery files
    all_found_pids = set()
    pid_pattern = re.compile(r'ChIJ[a-zA-Z0-9_-]{10,}')

    files_to_scan = list(recovery_dir.glob("*.txt")) + list(recovery_dir.glob("*.usv"))
    
    for f_path in files_to_scan:
        if f_path.name == "still_hollow_deduped.txt": continue
        print(f"Scanning {f_path.name}...")
        try:
            content = f_path.read_text()
            matches = pid_pattern.findall(content)
            all_found_pids.update(matches)
        except Exception as e:
            print(f"Error reading {f_path.name}: {e}")

    print(f"Extracted {len(all_found_pids)} unique Place IDs from recovery folder.")

    # 4. Check actual local index status using Pydantic validation
    actionable_hollow = set()
    hydrated_count = 0
    
    print(f"Validating {len(all_found_pids)} potential recovery targets against local index...")
    for pid in all_found_pids:
        # Skip if already in queue
        if pid in completed_ids or pid in pending_ids:
            continue
            
        local_file = index_dir / f"{pid}.usv"
        
        is_hollow = True
        if local_file.exists():
            try:
                # Read the last line (actual data)
                content = local_file.read_text().splitlines()
                if len(content) >= 2:
                    # Attempt Pydantic validation
                    # Note: from_usv handles unit separators and model constraints
                    GoogleMapsProspect.from_usv(content[-1])
                    is_hollow = False
                    hydrated_count += 1
            except Exception:
                # Validation failure = Hollow
                is_hollow = True
        
        if is_hollow:
            actionable_hollow.add(pid)

    # 5. Save
    output_path = recovery_dir / "still_hollow_deduped.txt"
    with open(output_path, 'w') as f:
        for pid in sorted(list(actionable_hollow)):
            f.write(f"{pid}\n")
    
    print("-" * 40)
    print(f"Scan complete.")
    print(f"  Already Hydrated (Validated): {hydrated_count}")
    print(f"  Actionable Hollow: {len(actionable_hollow)}")
    print(f"Saved deduplicated list to: {output_path}")

if __name__ == "__main__":
    compile_list()
