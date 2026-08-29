"""
Tile-Queue Processor: Converts map-tile/pending/ → discovery-gen/completed/

This processor reads tiles from map-tile/pending/, expands each tile
into individual ScrapeTask work items, writes them to discovery-gen/completed/
(ScrapeTask.SOURCE_QUEUE/SOURCE_STATE - discovery-gen's own permanent,
per-phrase-tile output, ready for a separate copy step into gm-list/pending/),
and marks the original tile as completed.

Pattern:
  Input:  map-tile/pending/{shard}/{lat}/{lon}/{tile_id}.usv
          (contains multiple TileQueueRecord lines: tile_id + phrase pairs)

  Output: discovery-gen/completed/{shard}/{lat}/{lon}/{phrase}.usv
          (individual ScrapeTask files, one per phrase per tile)

  Then:   Move tile file from pending/ → completed/ (map-tile has no
          processing phase - batching is via --max, not a staging move)
"""

import logging
from pathlib import Path
from typing import Any, List, Dict, Optional

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..core.queue.factory import get_queue_manager
from ..core.paths import paths
from ..models.campaigns.tile import TileRecord as TileQueueRecord
from ..models.campaigns.queues.gm_list import ScrapeTask

logger = logging.getLogger(__name__)


def process_tile_queue(
    campaign_name: str,
    max_tiles: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Process tiles from map-tile/pending/ → discovery-gen/completed/.

    Reads each tile file from pending/, converts its records to individual
    ScrapeTask work items, writes them to discovery-gen/completed/ with
    sharded structure, then moves the processed tile to map-tile/completed/.

    Args:
        campaign_name: Campaign to process
        max_tiles: Maximum number of tiles to process (None = all)
        dry_run: If True, don't write or move files

    Returns:
        Metrics: {tiles_processed, scrape_tasks_created, errors, identities}
        - identities: the normalized discovery-gen identity (see
          cocli/core/queue/reconcile.py) of every ScrapeTask this call
          actually wrote - this run's own authoritative "here's what I
          just created" list, for a caller to snapshot as a ScrapeJobRun's
          scope (job_run_service.py). Deliberately NOT a before/after
          directory diff - that would also catch an older, still-
          unfinished run's leftover items if two runs' generation windows
          overlap in time.

    Raises:
        ValueError: If campaign not found
    """
    from ..core.config import get_campaign_dir

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    # Get queue managers
    tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name=campaign_name)

    pending_dir = tile_queue.pending_dir
    completed_dir = tile_queue.completed_dir
    discovery_gen_completed = paths.campaign(campaign_name).queue(ScrapeTask.SOURCE_QUEUE).state(ScrapeTask.SOURCE_STATE)

    if not pending_dir.exists():
        logger.warning(f"Pending directory not found: {pending_dir}")
        return {"tiles_processed": 0, "scrape_tasks_created": 0, "errors": 0, "identities": []}

    logger.info(f"Processing map-tile for {campaign_name}")
    logger.info(f"  Input:  {pending_dir}")
    logger.info(f"  Output: {discovery_gen_completed}")

    tiles_processed = 0
    scrape_tasks_created = 0
    errors = 0
    identities: List[str] = []

    # Collect tile file paths up front (respecting max_tiles) so progress has a known total.
    import os
    tile_paths: List[Path] = []
    for root, dirs, files in os.walk(pending_dir):
        for filename in sorted(files):
            if filename.endswith(".usv"):
                tile_paths.append(Path(root) / filename)
        if max_tiles and len(tile_paths) >= max_tiles:
            break
    if max_tiles:
        tile_paths = tile_paths[:max_tiles]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        progress_task = progress.add_task(
            f"Processing tiles for {campaign_name}...", total=len(tile_paths)
        )

        for tile_path in tile_paths:
            filename = tile_path.name
            rel_path = tile_path.relative_to(pending_dir)

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
                    progress.advance(progress_task)
                    continue

                logger.debug(
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
                            rel = task_path.relative_to(discovery_gen_completed)
                            identities.append("/".join(rel.with_suffix("").parts[1:]))
                            logger.debug(f"  Created: {rel}")

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
                        logger.debug(f"Completed tile: {filename}")

                    except Exception as move_err:
                        logger.error(f"Error moving tile to completed: {move_err}")
                        errors += 1
                        progress.advance(progress_task)
                        continue

                tiles_processed += 1

            except Exception as e:
                logger.error(f"Error processing tile {filename}: {e}")
                errors += 1
                progress.advance(progress_task)
                continue

            progress.update(
                progress_task,
                advance=1,
                description=f"Processing tiles for {campaign_name}... ({scrape_tasks_created} tasks created)",
            )

    # CRITICAL: Create datapackage.json for schema compliance
    # Describes all *.usv ScrapeTask files in discovery-gen/completed using glob pattern
    if not dry_run:
        try:
            ScrapeTask.save_datapackage(
                discovery_gen_completed,
                resource_name="discovery-gen-completed",
                resource_path="**/*.usv",  # Glob pattern for all sharded files
                force=True,  # Overwrite if exists (safe for idempotent processing)
            )
            logger.info(f"  Created datapackage.json for {scrape_tasks_created} ScrapeTask records")
        except Exception as e:
            logger.error(f"Error creating datapackage.json in {discovery_gen_completed}: {e}")
            # Don't fail the entire processing if schema metadata fails
            errors += 1

    logger.info(
        f"Tile-queue processing complete: "
        f"{tiles_processed} tiles, {scrape_tasks_created} ScrapeTask records, {errors} errors"
    )

    return {
        "tiles_processed": tiles_processed,
        "scrape_tasks_created": scrape_tasks_created,
        "errors": errors,
        "identities": identities,
    }
