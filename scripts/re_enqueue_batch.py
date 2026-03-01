# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
import shutil
import sys
from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.gm_details import GmItemTask

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("re_enqueue")

async def re_enqueue_batch(campaign_name: str, target_file_name: str) -> None:
    batch_file = paths.campaign(campaign_name).path / "recovery" / target_file_name
    if not batch_file.exists():
        logger.error(f"Target file not found: {batch_file}")
        return

    # 1. Clear Local Pending Queue (Ensures a clean test run)
    pending_dir = paths.queue(campaign_name, "gm-details").pending
    if pending_dir.exists():
        logger.info(f"Clearing local pending queue: {pending_dir}")
        shutil.rmtree(pending_dir)
    pending_dir.mkdir(parents=True, exist_ok=True)

    # 2. Load Targets
    from typing import Dict, List, Union
    targets: List[Dict[str, Union[str, None]]] = []
    with open(batch_file, "r") as f:
        for line in f:
            if line.strip():
                parts = line.strip().split("|")
                if len(parts) >= 4:
                    # Canonical Format: pid|slug|name|gmb_url
                    targets.append({
                        "place_id": parts[0],
                        "slug": parts[1],
                        "name": parts[2],
                        "gmb_url": parts[3]
                    })
                elif len(parts) >= 3:
                    # Legacy Format: pid|slug|name
                    targets.append({
                        "place_id": parts[0],
                        "slug": parts[1],
                        "name": parts[2],
                        "gmb_url": None
                    })

    logger.info(f"Enqueuing {len(targets)} targets locally...")
    
    # 3. Enqueue (Forcing local filesystem mode)
    queue_manager = get_queue_manager("details", use_cloud=False, queue_type="gm_list_item", campaign_name=campaign_name)
    
    for t in targets:
        pid = t.get("place_id")
        slug = t.get("slug")
        name = t.get("name")
        
        if not pid or not slug or not name:
            continue

        task = GmItemTask(
            place_id=str(pid),
            campaign_name=campaign_name,
            company_slug=str(slug),
            name=str(name),
            gmb_url=t.get("gmb_url"),
            force_refresh=True
        )
        queue_manager.push(task)

    logger.info(f"Successfully enqueued {len(targets)} tasks from {target_file_name}")

if __name__ == "__main__":
    # Usage: python3 scripts/re_enqueue_batch.py [filename]
    batch_name = sys.argv[1] if len(sys.argv) > 1 else "recovery_targets.txt"
    asyncio.run(re_enqueue_batch("roadmap", batch_name))
