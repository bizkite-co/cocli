# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
import shutil
from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.gm_details import GmItemTask

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("re_enqueue")

async def re_enqueue_batch(campaign_name: str) -> None:
    batch_file = paths.campaign(campaign_name).path / "recovery" / "recovery_batch_200.txt"
    if not batch_file.exists():
        logger.error(f"Batch file not found: {batch_file}")
        return

    # 1. Clear Local Pending Queue
    pending_dir = paths.queue(campaign_name, "gm-details").pending
    if pending_dir.exists():
        logger.info(f"Clearing local pending queue: {pending_dir}")
        shutil.rmtree(pending_dir)
    pending_dir.mkdir(parents=True, exist_ok=True)

    # 2. Load Targets
    targets = []
    with open(batch_file, "r") as f:
        for line in f:
            if line.strip():
                parts = line.strip().split("|")
                if len(parts) >= 3:
                    pid = parts[0]
                    slug = parts[1]
                    name = "|".join(parts[2:]) # Recombine if name had |
                    targets.append({"place_id": pid, "slug": slug, "name": name})

    logger.info(f"Enqueuing {len(targets)} targets locally...")
    
    # 3. Enqueue Locally (Local-First Mandate)
    queue_manager = get_queue_manager("details", use_cloud=False, queue_type="gm_list_item", campaign_name=campaign_name)
    
    for t in targets:
        task = GmItemTask(
            place_id=t["place_id"],
            campaign_name=campaign_name,
            company_slug=t["slug"],
            name=t["name"],
            force_refresh=True
        )
        queue_manager.push(task)

    logger.info(f"Successfully enqueued {len(targets)} tasks for local run.")

if __name__ == "__main__":
    asyncio.run(re_enqueue_batch("roadmap"))
