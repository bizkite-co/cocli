#!/usr/bin/env python3
import os
import re
import sys
import logging
from typing import Set

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.core.config import get_campaign, get_campaign_dir

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def compile_list(campaign_name: str) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    recovery_dir = campaign_dir / "recovery"
    completed_dir = campaign_dir / "queues" / "gm-details" / "completed"
    pending_dir = campaign_dir / "queues" / "gm-details" / "pending"
    index_dir = campaign_dir / "indexes" / "google_maps_prospects"
    
    # 1. Get already completed valid IDs (to exclude)
    completed_ids: Set[str] = set()
    if completed_dir.exists():
        for f in completed_dir.glob("*.json"):
            completed_ids.add(f.stem)
    logger.info(f"Loaded {len(completed_ids)} already-completed valid IDs.")

    # 2. Get currently pending IDs (to avoid re-enqueuing)
    pending_ids: Set[str] = set()
    if pending_dir.exists():
        for f in pending_dir.glob("*/*/task.json"):
            pending_ids.add(f.parent.name)
    logger.info(f"Loaded {len(pending_ids)} currently pending IDs.")

    # 3. Extract PIDs from all recovery files
    all_found_pids: Set[str] = set()
    pid_pattern = re.compile(r'ChIJ[a-zA-Z0-9_-]{10,}')

    files_to_scan = list(recovery_dir.glob("*.txt")) + list(recovery_dir.glob("*.usv"))
    
    for f_path in files_to_scan:
        if f_path.name == "still_hollow_deduped.txt":
            continue
        logger.info(f"Scanning {f_path.name}...")
        try:
            content = f_path.read_text()
            matches = pid_pattern.findall(content)
            all_found_pids.update(matches)
        except Exception as e:
            logger.error(f"Error reading {f_path.name}: {e}")

    logger.info(f"Extracted {len(all_found_pids)} unique Place IDs from recovery folder.")

    # 4. Check actual local index status using Pydantic validation
    actionable_hollow: Set[str] = set()
    hydrated_count = 0
    
    logger.info(f"Validating {len(all_found_pids)} potential recovery targets against local index...")
    for pid in all_found_pids:
        # Skip if already in queue
        if pid in completed_ids or pid in pending_ids:
            continue
            
        # Check sharded path
        from cocli.core.sharding import get_place_id_shard
        shard = get_place_id_shard(pid)
        local_file = index_dir / shard / f"{pid}.usv"
        
        is_hollow = True
        if local_file.exists():
            try:
                # Attempt Pydantic validation
                GoogleMapsProspect.from_usv(local_file.read_text())
                is_hollow = False
                hydrated_count += 1
            except Exception:
                is_hollow = True
        
        if is_hollow:
            actionable_hollow.add(pid)

    # 5. Save
    output_path = recovery_dir / "still_hollow_deduped.txt"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f_out:
        for pid in sorted(list(actionable_hollow)):
            f_out.write(f"{pid}\n")
    
    logger.info("-" * 40)
    logger.info("Scan complete.")
    logger.info(f"  Already Hydrated (Validated): {hydrated_count}")
    logger.info(f"  Actionable Hollow: {len(actionable_hollow)}")
    logger.info(f"Saved deduplicated list to: {output_path}")

if __name__ == "__main__":

    from cocli.core.config import get_campaign

    camp = get_campaign() or "roadmap"

    compile_list(camp)
