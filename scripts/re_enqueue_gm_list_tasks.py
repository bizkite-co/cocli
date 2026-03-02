# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
import shutil
from cocli.core.paths import paths
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.gm_list import ScrapeTask

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("re_enqueue_gm_list")

async def re_enqueue_gm_list_tasks(campaign_name: str, target_file_name: str = "recovery_gm_list_tasks.txt") -> None:
    batch_file = paths.campaign(campaign_name).path / "recovery" / target_file_name
    if not batch_file.exists():
        logger.error(f"Target file not found: {batch_file}")
        return

    # 1. Clear Local Discovery Gen Index (Where GM List tasks live)
    discovery_gen = paths.campaign(campaign_name).queue("discovery-gen")
    mission_dir = discovery_gen.completed
    if mission_dir.exists():
        logger.info(f"Clearing local discovery-gen completed index: {mission_dir}")
        shutil.rmtree(mission_dir)
    mission_dir.mkdir(parents=True, exist_ok=True)

    # 2. Load Targets (Format: lat|lon|phrase|tile_id)
    tasks = []
    with open(batch_file, "r") as f:
        for line in f:
            if line.strip():
                lat, lon, phrase, tid = line.strip().split("|")
                tasks.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "phrase": phrase,
                    "tile_id": tid
                })

    logger.info(f"Enqueuing {len(tasks)} GM List tasks locally...")
    
    # 3. Enqueue
    queue_manager = get_queue_manager("scrape_tasks", use_cloud=False, queue_type="scrape", campaign_name=campaign_name)
    
    for t in tasks:
        task = ScrapeTask(
            latitude=float(str(t["lat"])),
            longitude=float(str(t["lon"])),
            zoom=15,
            search_phrase=str(t["phrase"]),
            campaign_name=campaign_name,
            tile_id=str(t["tile_id"]),
            force_refresh=True,
            ack_token=None
        )
        queue_manager.push(task)

    logger.info(f"Successfully enqueued {len(tasks)} GM List tasks from {target_file_name}")

if __name__ == "__main__":
    asyncio.run(re_enqueue_gm_list_tasks("roadmap"))
