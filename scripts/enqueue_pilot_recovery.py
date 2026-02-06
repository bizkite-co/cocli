#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.models.gm_item_task import GmItemTask
from cocli.core.text_utils import slugify

# Unit separator is \x1f
US = "\x1f"

def enqueue_pilot():
    campaign = "roadmap"
    recovery_map = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/recovery/consolidated_pid_name_map.usv")
    pending_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/queues/gm-details/pending")
    
    if not recovery_map.exists():
        print(f"Error: {recovery_map} not found.")
        return

    print(f"Reading pilot targets from {recovery_map.name}...")
    with open(recovery_map, 'r') as f:
        lines = [next(f) for _ in range(10)]

    for line in lines:
        parts = line.strip().split(US)
        if len(parts) < 2:
            continue
            
        place_id = parts[0]
        name = parts[1]
        slug = slugify(name)
        
        # Create Task
        task = GmItemTask(
            place_id=place_id,
            campaign_name=campaign,
            name=name,
            company_slug=slug,
            force_refresh=True,
            discovery_phrase="RECOVERY",
            discovery_tile_id="RECOVERY_BATCH_20260205"
        )
        
        # Save to sharded pending queue
        # Path: pending/<shard>/<place_id>/task.json
        shard = place_id[-2:]
        task_dir = pending_dir / shard / place_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        task_file = task_dir / "task.json"
        task_file.write_text(task.model_dump_json(indent=2))
        
        print(f"  Enqueued: {place_id} ({name})")

    print("-" * 40)
    print("Pilot enqueue complete. PIs should pick these up shortly.")

if __name__ == "__main__":
    enqueue_pilot()
