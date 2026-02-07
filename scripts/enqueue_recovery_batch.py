#!/usr/bin/env python3
import os
import sys
import logging
from typing import List, Dict

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.core.queue.factory import get_queue_manager
from cocli.models.gm_item_task import GmItemTask
from cocli.core.text_utils import slugify

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def enqueue_batch(batch: List[str], pid_to_name: Dict[str, str], campaign: str) -> None:
    logger.info(f"Processing batch of {len(batch)}...")

    queue_manager = get_queue_manager("gm-details", queue_type="details", campaign_name=campaign)
    enqueued_count = 0
    for pid in batch:
        # Use real name if known, otherwise placeholder
        name = pid_to_name.get(pid, f"Recovery Task {pid}")
        slug = slugify(name)
        
        # Identity tripod check (min_length=3)
        if len(name) < 3:
            name = f"PID {pid}"
        if len(slug) < 3:
            slug = f"pid-{pid.lower()}"

        task = GmItemTask(
            place_id=pid,
            campaign_name=campaign,
            name=name,
            company_slug=slug,
            force_refresh=True,
            discovery_phrase="RECOVERY_PRO-BATCH_500",
            discovery_tile_id="BATCH_20260205_2255"
        )
        
        queue_manager.push(task)
        enqueued_count += 1

    logger.info(f"Successfully enqueued {enqueued_count} tasks for campaign '{campaign}'.")

if __name__ == "__main__":
    # This script is usually called by a manager, but if run directly:
    logger.warning("This script is usually called by a manager script.")
