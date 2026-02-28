# POLICY: frictionless-data-policy-enforcement
import logging
from pathlib import Path
from cocli.core.paths import paths
from cocli.models.campaigns.queues.gm_list import ScrapeTask
from cocli.core.queue.factory import get_queue_manager

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("re_enqueue_tiles")

def re_enqueue_5_tiles(campaign_name: str):
    output_path = paths.campaign(campaign_name).path / "recovery" / "recovery_list_tiles_5.txt"
    
    # 5 Tiles identified from completed results
    tiles = [
        {"lat": 29.9, "lon": -98.9, "phrase": "pacific-life"},
        {"lat": 29.9, "lon": -97.5, "phrase": "financial-advisor"},
        {"lat": 29.9, "lon": -97.5, "phrase": "pacific-life"},
        {"lat": 29.9, "lon": -82.0, "phrase": "pacific-life"},
        {"lat": 29.9, "lon": -98.5, "phrase": "financial-advisor"}
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for t in tiles:
            f.write(f"{t['lat']}|{t['lon']}|{t['phrase']}\n")
    
    logger.info(f"Target list created: {output_path}")

    # Initialize Local Queue
    queue_manager = get_queue_manager("scrape_tasks", use_cloud=False, queue_type="scrape", campaign_name=campaign_name)
    
    # Enqueue
    for t in tiles:
        task = ScrapeTask(
            latitude=t["lat"],
            longitude=t["lon"],
            zoom=15,
            search_phrase=t["phrase"],
            campaign_name=campaign_name,
            tile_id=f"{t['lat']}_{t['lon']}",
            force_refresh=True
        )
        queue_manager.push(task)
        logger.info(f"  [ENQUEUED] {t['phrase']} @ {t['lat']}, {t['lon']}")

    logger.info(f"Successfully enqueued 5 discovery tasks locally.")

if __name__ == "__main__":
    re_enqueue_5_tiles("roadmap")
