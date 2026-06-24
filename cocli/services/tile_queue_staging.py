"""
Staging service: converts frontier.usv (MissionTask) → tile-queue (TileRecord).

This is the entry point to the tile-queue. It reads the frontier of pending
missions and decomposes them into atomic per-tile work units.

Pattern: frontier.usv (MissionTask, many tasks per tile)
         ↓ [grouping by tile_id]
         tile-queue/pending/tiles/*.usv (TileRecord, all phrases for one tile per file)
"""

import logging
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

from ..models.campaigns.mission import MissionTask
from ..models.campaigns.tile import TileRecord
from ..core.queue.factory import get_queue_manager
from ..core.paths import paths

logger = logging.getLogger(__name__)


def stage_frontier_to_tiles(campaign_name: str, force: bool = False) -> Dict[str, int]:
    """
    Stage frontier.usv → tile-queue work units.

    Reads discovery-gen/pending/frontier.usv, groups tasks by tile_id,
    and creates one USV file per tile in tile-queue/pending/tiles/.

    Returns metrics: {tiles_created, tiles_skipped, total_tasks}
    """
    # 1. Initialize queues (auto-creates directories and datapackage.json)
    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    tile_queue = get_queue_manager("tile-queue", queue_type="tile", campaign_name=campaign_name)

    # 2. Load frontier.usv
    frontier_file = dg_queue.pending / "frontier.usv"
    if not frontier_file.exists():
        logger.warning(f"Frontier not found: {frontier_file}")
        return {"tiles_created": 0, "tiles_skipped": 0, "total_tasks": 0}

    logger.info(f"Reading frontier: {frontier_file}")

    # 3. Group tasks by tile_id
    tiles: Dict[str, List[MissionTask]] = defaultdict(list)
    total_tasks = 0

    with open(frontier_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                mission_task = MissionTask.from_usv(line)
                tiles[mission_task.tile_id].append(mission_task)
                total_tasks += 1
            except Exception as e:
                logger.error(f"Error parsing frontier line: {e}")
                continue

    logger.info(f"Grouped {total_tasks} tasks into {len(tiles)} tiles")

    # 4. Create per-tile files in tile-queue/pending/tiles/
    tiles_created = 0
    tiles_skipped = 0

    for tile_id, tasks in sorted(tiles.items()):
        # Safe filename from tile_id: 28.3_-81.4 → 28_3_m81_4
        safe_tile_name = tile_id.replace(".", "_").replace("-", "m")
        tile_file = tile_queue.tiles_dir / f"{tile_id}.usv"

        if tile_file.exists() and not force:
            logger.debug(f"Tile file already exists (skipping): {tile_file.name}")
            tiles_skipped += 1
            continue

        try:
            # Write all tasks for this tile to the file
            with open(tile_file, "w", encoding="utf-8") as f:
                for task in tasks:
                    # Convert MissionTask → TileRecord
                    tile_record = TileRecord(
                        tile_id=task.tile_id,
                        search_phrase=task.search_phrase,
                        latitude=task.latitude,
                        longitude=task.longitude,
                    )
                    f.write(tile_record.to_usv())

            logger.info(f"Created tile file: {tile_file.name} ({len(tasks)} tasks)")
            tiles_created += 1

            # Register with queue
            tile_queue.push(tile_file)

        except Exception as e:
            logger.error(f"Error creating tile file {tile_file.name}: {e}")
            continue

    logger.info(f"Staging complete: {tiles_created} created, {tiles_skipped} skipped, {total_tasks} tasks")
    return {
        "tiles_created": tiles_created,
        "tiles_skipped": tiles_skipped,
        "total_tasks": total_tasks,
    }
