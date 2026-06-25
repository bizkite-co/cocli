"""
Tile-Queue Processor: Converts tile-queue/processing/ → gm-list/pending/

This processor reads tiles from tile-queue/processing/, expands each tile
into individual ScrapeTask work items, writes them to gm-list/pending/,
and marks the original tile as completed.

Pattern:
  Input:  tile-queue/processing/{shard}/{lat}/{lon}/{tile_id}.usv
          (contains multiple TileQueueRecord lines: tile_id + phrase pairs)

  Output: gm-list/pending/{shard}/{lat}/{lon}/{phrase}.usv
          (individual ScrapeTask files, one per phrase per tile)

  Then:   Move tile file from processing/ → completed/
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional

from ..core.queue.factory import get_queue_manager
from ..core.paths import paths
from ..models.campaigns.tile import TileRecord as TileQueueRecord
from ..models.campaigns.queues.gm_list import ScrapeTask

logger = logging.getLogger(__name__)


def process_tile_queue(
    campaign_name: str,
    max_tiles: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Process tiles from tile-queue/processing/ → gm-list/pending/.

    Reads each tile file from processing/, converts its records to individual
    ScrapeTask work items, writes them to gm-list/pending/ with sharded structure,
    then moves the processed tile to completed/.

    Args:
        campaign_name: Campaign to process
        max_tiles: Maximum number of tiles to process (None = all)
        dry_run: If True, don't write or move files

    Returns:
        Metrics: {tiles_processed, scrape_tasks_created, errors}

    Raises:
        ValueError: If campaign not found
    """
    from ..core.config import get_campaign_dir

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    # Get queue managers
    tile_queue = get_queue_manager("tile-queue", queue_type="tile", campaign_name=campaign_name)
    gm_list_queue = get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_name)

    processing_dir = tile_queue.processing_dir
    completed_dir = tile_queue.completed_dir
    gm_list_pending = paths.campaign(campaign_name).queue("gm-list").pending

    if not processing_dir.exists():
        logger.warning(f"Processing directory not found: {processing_dir}")
        return {"tiles_processed": 0, "scrape_tasks_created": 0, "errors": 0}

    logger.info(f"Processing tile-queue for {campaign_name}")
    logger.info(f"  Input:  {processing_dir}")
    logger.info(f"  Output: {gm_list_pending}")

    tiles_processed = 0
    scrape_tasks_created = 0
    errors = 0

    # Walk through tile-queue/processing/{shard}/{lat}/{lon}/*.usv
    import os
    for root, dirs, files in os.walk(processing_dir):
        if max_tiles and tiles_processed >= max_tiles:
            break

        for filename in sorted(files):
            if not filename.endswith(".usv"):
                continue

            if max_tiles and tiles_processed >= max_tiles:
                break

            tile_path = Path(root) / filename
            rel_path = tile_path.relative_to(processing_dir)

            try:
                # 1. Read tile file and parse TileQueueRecords
                tile_records: List[TileQueueRecord] = []
                with open(tile_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                record = TileQueueRecord.from_usv(line)
                                tile_records.append(record)
                            except Exception as parse_err:
                                logger.error(f"Error parsing line in {filename}: {parse_err}")
                                errors += 1
                                continue

                if not tile_records:
                    logger.warning(f"Tile file has no records: {filename}")
                    errors += 1
                    continue

                logger.info(
                    f"Processing tile: {filename} ({len(tile_records)} phrases)"
                )

                # 2. Convert each TileQueueRecord → ScrapeTask and write to gm-list/pending/
                if not dry_run:
                    for record in tile_records:
                        try:
                            # Create ScrapeTask
                            scrape_task = ScrapeTask(
                                latitude=record.latitude,
                                longitude=record.longitude,
                                zoom=15.0,
                                search_phrase=record.search_phrase,
                                campaign_name=campaign_name,
                                tile_id=record.tile_id,
                            )

                            # Get gm-list pending path from ScrapeTask
                            task_path = scrape_task.get_local_path()

                            # Create directory and write task file
                            task_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(task_path, "w", encoding="utf-8") as f:
                                f.write(scrape_task.to_usv())

                            scrape_tasks_created += 1
                            logger.debug(f"  Created: {task_path.relative_to(gm_list_pending)}")

                        except Exception as task_err:
                            logger.error(
                                f"Error creating ScrapeTask for {record.tile_id}/"
                                f"{record.search_phrase}: {task_err}"
                            )
                            errors += 1
                            continue

                # 3. Move processed tile from processing/ → completed/
                if not dry_run:
                    try:
                        completed_dir.mkdir(parents=True, exist_ok=True)
                        completed_path = completed_dir / rel_path

                        # Create subdirectories in completed/
                        completed_path.parent.mkdir(parents=True, exist_ok=True)

                        # Move (rename) the file
                        tile_path.rename(completed_path)
                        logger.info(f"Completed tile: {filename}")

                    except Exception as move_err:
                        logger.error(f"Error moving tile to completed: {move_err}")
                        errors += 1
                        continue

                tiles_processed += 1

            except Exception as e:
                logger.error(f"Error processing tile {filename}: {e}")
                errors += 1
                continue

    logger.info(
        f"Tile-queue processing complete: "
        f"{tiles_processed} tiles, {scrape_tasks_created} ScrapeTask records, {errors} errors"
    )

    return {
        "tiles_processed": tiles_processed,
        "scrape_tasks_created": scrape_tasks_created,
        "errors": errors,
    }
