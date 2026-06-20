"""
Discovery-Gen Pipeline Stages: Decomposed, testable functions.

Stage 1: generate_tiles()
Stage 2: expand_phrases()
Stage 3: filter_frontier()
Stage 4: create_batch()
"""

import logging
import csv
from typing import List, Dict, Any, Optional
from pathlib import Path
import toml

from cocli.core.paths import paths
from cocli.core.config import get_campaign_dir
from cocli.core.geo_types import LatScale1, LonScale1
from cocli.planning.generate_grid import get_campaign_grid_tiles
from cocli.models.campaigns.tiles import TileRecord
from cocli.models.campaigns.target_location import TargetLocationRecord
from cocli.models.campaigns.mission import MissionTask
from cocli.core.scrape_index import ScrapeIndex

logger = logging.getLogger(__name__)


def generate_tiles(
    campaign_name: str,
    target_locations: Optional[List[Dict[str, Any]]] = None,
    proximity_miles: float = 10.0,
    save_output: bool = False,
) -> List[TileRecord]:
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


def _load_target_locations(campaign_name: str) -> List[Dict[str, Any]]:
    """Load target locations from inputs/target_locations.usv or config."""
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found: {campaign_name}")

    # First try inputs directory
    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    inputs_path = dg_queue.inputs / "target_locations.usv"

    target_locations: List[Dict[str, Any]] = []

    if inputs_path.exists():
        logger.info(f"  Loading target locations from: {inputs_path}")
        with open(inputs_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    parts = line.strip().split("\x1f")
                    if len(parts) == 3:
                        target_locations.append(
                            {
                                "name": parts[0],
                                "lat": float(parts[1]),
                                "lon": float(parts[2]),
                            }
                        )
    else:
        # Fall back to config file
        with open(campaign_dir / "config.toml", "r") as f:
            config = toml.load(f)

        prospecting_config = config.get("prospecting", {})
        target_locations_csv = prospecting_config.get("target-locations-csv")

        if target_locations_csv:
            path = campaign_dir / target_locations_csv
            if not path.exists():
                path = campaign_dir / "resources" / target_locations_csv

            if path.exists():
                logger.info(f"  Loading target locations from config: {path}")
                with open(path, "r", encoding="utf-8") as f:
                    if path.suffix == ".usv":
                        from cocli.utils.usv_utils import USVDictReader

                        u_reader = USVDictReader(f)
                        rows = list(u_reader)
                    else:
                        c_reader = csv.DictReader(f)
                        rows = list(c_reader)

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

    if not target_locations:
        raise ValueError(f"No target locations found for {campaign_name}")

    return target_locations


def expand_phrases(
    campaign_name: str,
    tiles: Optional[List[TileRecord]] = None,
    save_output: bool = True,
) -> List[MissionTask]:
    """
    Stage 2: Expand tiles × search phrases → mission tasks.

    Args:
        campaign_name: Campaign to generate mission for
        tiles: List of TileRecord objects. If None, loads from inputs/tiles.usv
        save_output: If True, saves to mission.usv with datapackage.json

    Returns:
        List of MissionTask objects
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
    tasks: List[MissionTask] = []
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
    mission_tasks: Optional[List[MissionTask]] = None,
    ttl_days: int = 30,
    save_output: bool = True,
) -> List[MissionTask]:
    """
    Stage 3: Filter mission tasks by ScrapeIndex to find unscraped frontier.

    Args:
        campaign_name: Campaign to filter for
        mission_tasks: List of MissionTask objects. If None, loads from mission.usv
        ttl_days: Tiles scraped longer ago than this are considered stale
        save_output: If True, saves to pending/frontier.usv

    Returns:
        List of unscraped/stale MissionTask objects (the frontier)
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

    for task in mission_tasks:
        match = scrape_index.is_tile_scraped(
            task.search_phrase, task.tile_id, ttl_days=ttl_days
        )

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
