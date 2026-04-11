#!/usr/bin/env python3
import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.core.config import get_campaign, get_campaign_dir
from cocli.core.queue.factory import get_queue_manager
from cocli.models.campaigns.queues.gm_details import GmItemTask
from cocli.core.text_utils import slugify

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def enqueue_pilot(campaign_name: str) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    recovery_dir = campaign_dir / "recovery"
    plan_file = recovery_dir / "still_hollow_deduped.txt"
    
    if not plan_file.exists():
        logger.error(f"Recovery plan not found: {plan_file}")
        return

    # Load first 500
    with open(plan_file, 'r') as f:
        all_pids = [line.strip() for line in f if line.strip()]
    
    batch = all_pids[:500]
    logger.info(f"Enqueuing pilot batch of {len(batch)} items...")

    queue_manager = get_queue_manager("gm-details", queue_type="details", campaign_name=campaign_name)
    
    count = 0
    for pid in batch:
        task = GmItemTask(
            place_id=pid,
            campaign_name=campaign_name,
            name=f"Pilot Recovery {pid}",
            company_slug=slugify(f"pilot-recovery-{pid}"),
            force_refresh=True,
            discovery_phrase="PILOT_RECOVERY",
            discovery_tile_id="BATCH_20260206_1200"
        )
        queue_manager.push(task)
        count += 1

    logger.info(f"Successfully enqueued {count} pilot recovery tasks.")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    enqueue_pilot(get_campaign() or "roadmap")