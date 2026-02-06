#!/usr/bin/env python3
import os
import sys
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.models.gm_item_task import GmItemTask
from cocli.core.text_utils import slugify

# Unit separator is \x1f
US = "\x1f"

def enqueue_batch(batch_size=500):
    campaign = "roadmap"
    recovery_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/recovery")
    still_hollow_file = recovery_dir / "still_hollow_deduped.txt"
    name_map_file = recovery_dir / "consolidated_pid_name_map.usv"
    pending_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/queues/gm-details/pending")
    
    if not still_hollow_file.exists():
        print(f"Error: {still_hollow_file} not found.")
        return

    # 1. Load Name Map
    pid_to_name = {}
    if name_map_file.exists():
        with open(name_map_file, 'r') as f:
            for line in f:
                parts = line.strip().split(US)
                if len(parts) >= 2:
                    pid_to_name[parts[0]] = parts[1]
    print(f"Loaded {len(pid_to_name)} known names from map.")

    # 2. Read actionable targets
    with open(still_hollow_file, 'r') as f:
        all_targets = [line.strip() for line in f if line.strip()]
    
    print(f"Found {len(all_targets)} total actionable targets.")
    if not all_targets:
        print("No targets left to process.")
        return

    batch = all_targets[:batch_size]
    print(f"Processing batch of {len(batch)}...")

    enqueued_count = 0
    for pid in batch:
        # Use real name if known, otherwise placeholder
        name = pid_to_name.get(pid, f"Recovery Task {pid}")
        slug = slugify(name)
        
        # Identity tripod check (min_length=3)
        if len(name) < 3: name = f"PID {pid}"
        if len(slug) < 3: slug = f"pid-{pid.lower()}"

        task = GmItemTask(
            place_id=pid,
            campaign_name=campaign,
            name=name,
            company_slug=slug,
            force_refresh=True,
            discovery_phrase="RECOVERY_PRO-BATCH_500",
            discovery_tile_id="BATCH_20260205_2255"
        )
        
        # Save to sharded pending queue
        shard = pid[-2:]
        task_dir = pending_dir / shard / pid
        task_dir.mkdir(parents=True, exist_ok=True)
        
        task_file = task_dir / "task.json"
        task_file.write_text(task.model_dump_json(indent=2))
        enqueued_count += 1

    # 3. Update the source list (remove the 500 we just enqueued)
    remaining = all_targets[batch_size:]
    with open(still_hollow_file, 'w') as f:
        for pid in remaining:
            f.write(f"{pid}\n")

    print("-" * 40)
    print(f"Successfully enqueued {enqueued_count} tasks.")
    print(f"Remaining in list: {len(remaining)}")

if __name__ == "__main__":
    enqueue_batch(500)