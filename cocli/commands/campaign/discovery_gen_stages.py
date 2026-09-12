"""
Discovery-Gen Pipeline Stages: Decomposed, testable functions.

ARCHITECTURE:
  The discovery-gen pipeline transforms target locations → tiles → mission tasks → frontier.
  Each stage is independently testable and can chain input/output via USV files.

STAGES:
  Stage 1: generate_tiles(campaign_name) → List[TileRecord]
    Input: target_locations from config or inputs/target_locations.usv
    Output: tiles.usv (saved to tiles/ with datapackage.json schema)
    Purpose: Create geographic grid covering target locations

  Stage 2: expand_phrases(campaign_name, tiles) → List[MissionTask]
    Input: TileRecord list from Stage 1
    Output: mission.usv (saved to queue root with datapackage.json)
    Purpose: Cross tiles × search phrases from config to create mission tasks

  Stage 3: filter_frontier(campaign_name, mission_tasks) → List[MissionTask]
    Input: MissionTask list from Stage 2
    Output: pending/frontier.usv (unscraped/stale tasks, with datapackage.json)
    Purpose: Filter by ScrapeIndex TTL to find pending work [DEPRECATED]

  Stage 4: populate_tile_queue(campaign_name, mission_tasks) → int
    Input: MissionTask list from Stage 2 (all tasks, no TTL filtering)
    Output: tile-queue/pending/{shard}/{lat}/{lon}/{tile_id}.usv (sharded USV files)
    Purpose: Write all mission tasks as the manifest for tile-queue processor
    Note: This bypasses frontier.usv and feeds directly into tile-queue

USAGE:
  # Full pipeline execution (all stages with file I/O):
  cocli dev run-discovery-gen-stages turboship

  # Single stage (e.g., just generate tiles):
  cocli dev run-discovery-gen-stages turboship --stage=1

  # Validate existing outputs:
  cocli dev run-discovery-pipeline turboship

TESTING:
  # All stages have unit tests with mocked dependencies
  pytest tests/unit/test_discovery_gen_stages.py

  # Schema conformance tests
  pytest tests/integration/test_discovery_gen_frictionless_validation.py

SCHEMA VERSIONING:
  Each stage output includes a datapackage.json with:
    - Frictionless Data schema (field names, types, descriptions)
    - cocli:schema_hash for deterministic version tracking
    - cocli:generated_at timestamp
  This prevents schema conflicts when outputs are stored in different directories.
"""
from __future__ import annotations

import logging
import csv
from pathlib import Path
from typing import Any, Optional
import toml

from cocli.core.paths import paths
from cocli.core.config import get_campaign_dir
from cocli.core.geo_types import LatScale1, LonScale1
from cocli.planning.generate_grid import get_campaign_grid_tiles
from cocli.models.campaigns.tiles import TileRecord
from cocli.models.campaigns.mission import MissionTask
from cocli.models.campaigns.tile import TileRecord as TileQueueRecord
from cocli.core.scrape_index import ScrapeIndex
from cocli.core.sharding import get_geo_shard

logger = logging.getLogger(__name__)


def generate_tiles(
    campaign_name: str,
    target_locations: Optional[list[dict[str, Any]]] = None,
    proximity_miles: float = 10.0,
    save_output: bool = False,
) -> list[TileRecord]:
    """
    Stage 1: Generate geographic grid tiles from target locations.

    If target_locations is not provided, loads from inputs/target_locations.usv.

    Args:
        campaign_name: Campaign to generate tiles for
        target_locations: List of dicts with 'lat', 'lon', 'name' keys. If None, loads from config.
        proximity_miles: Search radius for each location
        save_output: If True, saves to inputs/tiles.usv with datapackage.json

    Returns:
        List of TileRecord objects
    """
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    # Load target locations if not provided
    if target_locations is None:
        target_locations = _load_target_locations(campaign_name)

    logger.info(
        f"Stage 1: Generating grid for {len(target_locations)} locations (Radius: {proximity_miles} mi)..."
    )

    # Generate unique tiles
    unique_tiles = get_campaign_grid_tiles(
        campaign_name, target_locations=target_locations
    )

    logger.info(f"  Generated {len(unique_tiles)} unique tiles")

    # Convert to TileRecord objects
    tile_records = []
    for tile in unique_tiles:
        tile_id = tile.get("id")
        center_lat = tile.get("center_lat") or tile.get("center", {}).get("lat")
        center_lon = tile.get("center_lon") or tile.get("center", {}).get("lon")

        if tile_id and center_lat and center_lon:
            record = TileRecord(
                id=tile_id,
                center_lat=LatScale1(center_lat),
                center_lon=LonScale1(center_lon),
                zoom_level=tile.get("zoom_level"),
            )
            tile_records.append(record)

    # Save output if requested
    if save_output:
        dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
        tiles_dir = dg_queue.path / "tiles"
        tiles_path = tiles_dir / "tiles.usv"
        TileRecord.save_usv_with_datapackage(tile_records, tiles_path, "tiles")
        logger.info(f"  Saved tiles to: {tiles_path}")

    return tile_records


def _load_target_locations(campaign_name: str) -> list[dict[str, Any]]:
    """Load target locations, with config's target-locations-csv (when set)
    as the sole hand-edited source of truth.

    inputs/target_locations.usv is a *generated cache*, not a second source
    someone hand-maintains: when a CSV is configured, it always wins and this
    function overwrites the .usv from it before returning, so the two can
    never diverge (previously the .usv, if present, silently shadowed the
    CSV forever - editing the CSV had no effect once that file existed).
    Falls back to reading an existing .usv directly only when no CSV is
    configured, for campaigns that only ever had a hand-maintained .usv.
    """
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    inputs_path = dg_queue.inputs / "target_locations.usv"

    target_locations: list[dict[str, Any]] = []

    config_path = campaign_dir / "config.toml"
    target_locations_csv = None
    if config_path.exists():
        with open(config_path, "r") as f:
            config = toml.load(f)
        prospecting_config = config.get("prospecting", {})
        target_locations_csv = prospecting_config.get("target-locations-csv")

    csv_path: Optional[Path] = None
    if target_locations_csv:
        candidate = campaign_dir / target_locations_csv
        if not candidate.exists():
            candidate = campaign_dir / "resources" / target_locations_csv
        if candidate.exists():
            csv_path = candidate

    if csv_path is not None:
        logger.info(f"  Loading target locations from config-declared CSV: {csv_path}")
        with open(csv_path, "r", encoding="utf-8") as f:
            if csv_path.suffix == ".usv":
                from cocli.utils.usv_utils import USVDictReader

                rows = list(USVDictReader(f))
            else:
                rows = list(csv.DictReader(f))

        for row in rows:
            lat, lon = row.get("lat"), row.get("lon")
            if lat and lon:
                target_locations.append(
                    {
                        "name": row.get("name") or row.get("city"),
                        "lat": float(lat),
                        "lon": float(lon),
                    }
                )

        # Refresh the generated cache so the discovery-gen queue's own
        # inputs/ directory reflects the CSV that was just read - keeps the
        # two from ever being able to drift apart again.
        if csv_path.suffix != ".usv":
            from cocli.utils.usv_utils import csv_to_usv

            inputs_path.parent.mkdir(parents=True, exist_ok=True)
            csv_to_usv(str(csv_path), str(inputs_path))
        elif csv_path != inputs_path:
            import shutil

            inputs_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(csv_path, inputs_path)

    elif inputs_path.exists():
        logger.info(f"  No CSV configured; loading target locations from cache: {inputs_path}")
        with open(inputs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        def _as_headerless_triple(line: str) -> Optional[dict[str, Any]]:
            parts = line.strip().split("\x1f")
            if len(parts) != 3:
                return None
            try:
                return {"name": parts[0], "lat": float(parts[1]), "lon": float(parts[2])}
            except ValueError:
                return None

        first_data_line = next((line for line in lines if line.strip()), None)
        if first_data_line is not None and _as_headerless_triple(first_data_line) is not None:
            # Legacy headerless name\x1flat\x1flon format, one row per line.
            for line in lines:
                if line.strip():
                    triple = _as_headerless_triple(line)
                    if triple:
                        target_locations.append(triple)
        else:
            # Header + extra-column format (e.g. output of a geocoded CSV
            # import: name, beds, lat, lon, city, state, ...). USVDictReader
            # auto-detects the header row and hands back named fields - the
            # plain 3-field split above silently dropped every row (including
            # the header itself) whenever this richer shape showed up.
            import io

            from cocli.utils.usv_utils import USVDictReader

            for row in USVDictReader(io.StringIO("".join(lines))):
                lat, lon = row.get("lat"), row.get("lon")
                if lat and lon:
                    target_locations.append(
                        {
                            "name": row.get("name") or row.get("city"),
                            "lat": float(lat),
                            "lon": float(lon),
                        }
                    )

    if not target_locations:
        raise ValueError(f"No target locations found for {campaign_name}")

    return target_locations


def expand_phrases(
    campaign_name: str,
    tiles: Optional[list[TileRecord]] = None,
    save_output: bool = True,
) -> list[MissionTask]:
    """
    Stage 2: Expand tiles × search phrases → mission tasks.

    Reads search phrases from campaign config and creates one MissionTask
    per (tile, phrase) combination. Tasks are sorted by tile_id then phrase
    for deterministic output.

    Args:
        campaign_name: Campaign to generate mission for
        tiles: List of TileRecord objects. If None, loads from tiles/tiles.usv
        save_output: If True, saves to mission.usv at queue root with datapackage.json

    Returns:
        List of MissionTask objects (tile_id, search_phrase, latitude, longitude)

    Raises:
        ValueError: If campaign directory not found or tiles file missing

    Example:
        tiles = generate_tiles("turboship", save_output=True)
        mission = expand_phrases("turboship", tiles=tiles, save_output=True)
        # Creates mission.usv: tile_id<tab>phrase<tab>lat<tab>lon
    """
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    # Load tiles if not provided
    if tiles is None:
        dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
        tiles_path = dg_queue.path / "tiles" / "tiles.usv"
        if not tiles_path.exists():
            raise ValueError(f"Tiles file not found: {tiles_path}")

        tiles = []
        with open(tiles_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    tiles.append(TileRecord.from_usv(line))

    # Load config for search phrases
    with open(campaign_dir / "config.toml", "r") as f:
        config = toml.load(f)

    prospecting_config = config.get("prospecting", {})
    search_phrases = prospecting_config.get("queries", [])

    logger.info(
        f"Stage 2: Expanding {len(tiles)} tiles × {len(search_phrases)} phrases..."
    )

    # Create mission tasks
    tasks: list[MissionTask] = []
    for tile in tiles:
        for phrase in search_phrases:
            task = MissionTask(
                tile_id=tile.id,
                search_phrase=phrase,
                latitude=tile.center_lat,
                longitude=tile.center_lon,
            )
            tasks.append(task)

    # Sort by tile_id then phrase for stability
    tasks.sort(key=lambda x: (x.tile_id, x.search_phrase))

    logger.info(f"  Generated {len(tasks)} mission tasks")

    # Save output if requested
    if save_output:
        dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
        mission_path = dg_queue.master
        MissionTask.save_usv_with_datapackage(tasks, mission_path, "mission")
        logger.info(f"  Saved mission to: {mission_path}")

    return tasks


def filter_frontier(
    campaign_name: str,
    mission_tasks: Optional[list[MissionTask]] = None,
    ttl_days: int = 30,
    save_output: bool = True,
) -> list[MissionTask]:
    """
    Stage 3: Filter mission tasks by ScrapeIndex to find unscraped frontier.

    Queries ScrapeIndex to identify:
    1. Tasks never scraped (no match in index)
    2. Tasks stale beyond ttl_days (last scrape > ttl_days ago)
    3. Tasks in unproductive areas (no results found historically)

    Results are "the frontier" — pending work ready for scraping.

    Args:
        campaign_name: Campaign to filter for
        mission_tasks: List of MissionTask objects. If None, loads from mission.usv
        ttl_days: Tiles scraped longer ago than this are considered stale (default: 30)
        save_output: If True, saves to pending/frontier.usv with datapackage.json

    Returns:
        List of unscraped/stale MissionTask objects ready for scraping

    Raises:
        ValueError: If campaign directory not found or mission.usv missing

    Example:
        mission = expand_phrases("turboship", save_output=True)
        frontier = filter_frontier("turboship", mission_tasks=mission, save_output=True)
        # Creates pending/frontier.usv: MissionTask records ready to scrape
    """
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    # Load mission tasks if not provided
    if mission_tasks is None:
        dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
        mission_path = dg_queue.master
        if not mission_path.exists():
            raise ValueError(f"Mission file not found: {mission_path}")

        mission_tasks = []
        with open(mission_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    mission_tasks.append(MissionTask.from_usv(line))

    logger.info(
        f"Stage 3: Filtering {len(mission_tasks)} mission tasks (TTL: {ttl_days} days)..."
    )

    scrape_index = ScrapeIndex()
    pending_tasks = []
    match_count = 0
    skipped_unproductive = 0
    skipped_wilderness = 0

    for task in mission_tasks:
        match = scrape_index.is_tile_scraped(
            task.search_phrase, task.tile_id, ttl_days=ttl_days
        )

        if scrape_index.is_wilderness_tile(task.tile_id):
            skipped_wilderness += 1
            continue

        if not match:
            forever_match = scrape_index.is_tile_scraped(
                task.search_phrase, task.tile_id, ttl_days=None
            )
            if forever_match and forever_match.items_found == 0:
                skipped_unproductive += 1
                continue

            lat, lon = task.latitude, task.longitude
            bounds = {
                "lat_min": lat - 0.05,
                "lat_max": lat + 0.05,
                "lon_min": lon - 0.05,
                "lon_max": lon + 0.05,
            }
            area_match_res = scrape_index.is_area_scraped(
                task.search_phrase, bounds, ttl_days=ttl_days, overlap_threshold_percent=90.0
            )
            if area_match_res:
                area_match, _ = area_match_res
                if area_match.items_found == 0:
                    skipped_unproductive += 1
                    continue
                match = area_match

            if not match:
                pending_tasks.append(task)
            else:
                match_count += 1
        else:
            match_count += 1

    logger.info(f"  Identified {match_count} previously scraped tiles")
    if skipped_wilderness > 0:
        logger.info(f"  Skipped {skipped_wilderness} wilderness tiles")
    if skipped_unproductive > 0:
        logger.info(f"  Skipped {skipped_unproductive} unproductive tiles (0 results)")
    logger.info(f"  Frontier: {len(pending_tasks)} pending tasks")

    # Save output if requested
    if save_output:
        dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
        frontier_path = dg_queue.pending / "frontier.usv"
        MissionTask.save_usv_with_datapackage(pending_tasks, frontier_path, "frontier")
        logger.info(f"  Saved frontier to: {frontier_path}")

    return pending_tasks


def populate_tile_queue(
    campaign_name: str,
    mission_tasks: Optional[list[MissionTask]] = None,
    save_output: bool = True,
) -> int:
    """
    Stage 4: Write all mission tasks directly to tile-queue manifest.

    Reads mission.usv (all tasks, no TTL filtering) and writes to
    tile-queue/pending/{shard}/{lat}/{lon}/{tile_id}.usv files.
    This becomes the authoritative manifest for scraping.

    Args:
        campaign_name: Campaign to populate tile-queue for
        mission_tasks: List of MissionTask objects. If None, loads from mission.usv
        save_output: If True, writes to tile-queue/pending/{shard}/{lat}/{lon}/

    Returns:
        Number of tile files created

    Raises:
        ValueError: If campaign directory not found or mission.usv missing
    """
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    # Load mission tasks if not provided
    if mission_tasks is None:
        dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
        mission_path = dg_queue.master
        if not mission_path.exists():
            raise ValueError(f"Mission file not found: {mission_path}")

        mission_tasks = []
        with open(mission_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    mission_tasks.append(MissionTask.from_usv(line))

    logger.info(f"Stage 4: Populating map-tile with {len(mission_tasks)} mission tasks...")

    if not save_output:
        return len(mission_tasks)

    # Get map-tile base path
    tile_queue = paths.campaign(campaign_name).queue("map-tile")
    pending_dir = tile_queue.pending

    # Group tasks by (tile_id, shard, lat, lon)
    tile_files: dict[str, list[TileQueueRecord]] = {}

    for task in mission_tasks:
        shard = get_geo_shard(float(task.latitude))
        lat = str(task.latitude)
        lon = str(task.longitude)

        # File path: pending/{shard}/{lat}/{lon}/{tile_id}.usv
        rel_path = f"{shard}/{lat}/{lon}/{task.tile_id}.usv"

        if rel_path not in tile_files:
            tile_files[rel_path] = []

        # Create TileQueueRecord (tile + phrase)
        record = TileQueueRecord(
            tile_id=task.tile_id,
            search_phrase=task.search_phrase,
            latitude=task.latitude,
            longitude=task.longitude,
        )
        tile_files[rel_path].append(record)

    # Write sharded tile files
    tiles_created = 0
    for rel_path, records in sorted(tile_files.items()):
        file_path = pending_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(record.to_usv())

            logger.debug(f"  Created tile file: {rel_path} ({len(records)} phrases)")
            tiles_created += 1
        except Exception as e:
            logger.error(f"Error creating tile file {file_path}: {e}")
            continue

    # CRITICAL: Create datapackage.json for schema compliance
    # Describes all *.usv files in all shards using glob pattern
    try:
        TileQueueRecord.save_datapackage(
            pending_dir,
            resource_name="map-tile",
            resource_path="**/*.usv",  # Glob pattern for all sharded files
            force=True,  # Overwrite if exists (safe for idempotent processing)
        )
        logger.info(f"  Created datapackage.json for {tiles_created} tiles")
    except Exception as e:
        logger.error(f"Error creating datapackage.json in {pending_dir}: {e}")
        # Don't fail the entire stage if schema metadata fails
        pass

    logger.info(f"Stage 4 complete: {tiles_created} tile files created in {pending_dir}")
    return tiles_created
