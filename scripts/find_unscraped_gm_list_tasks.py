# POLICY: frictionless-data-policy-enforcement
import logging
from pathlib import Path
from typing import List, Any
from cocli.core.paths import paths
from cocli.core.text_utils import slugify
from cocli.core.sharding import get_geo_shard, get_grid_tile_id
from cocli.core.constants import UNIT_SEP

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("find_gm_list_tasks")

def is_hollow_usv(usv_path: Path) -> bool:
    """
    Returns True if the USV file exists but is missing critical high-fidelity data
    (ratings or review counts) in ALL rows.
    """
    if not usv_path.exists():
        return True
        
    try:
        content = usv_path.read_text(encoding="utf-8").strip()
        if not content:
            return True
            
        rows = content.splitlines()
        hollow_rows = 0
        for row in rows:
            fields = row.split(UNIT_SEP)
            # Schema: 0: pid, 1: slug, 2: name, 3: phone, 4: domain, 5: reviews, 6: rating, 7: address, 8: gmb_url
            reviews = fields[5] if len(fields) > 5 else ""
            rating = fields[6] if len(fields) > 6 else ""
            
            if not reviews or not rating:
                hollow_rows += 1
        
        # If all rows are hollow, the file is hollow
        return hollow_rows == len(rows)
    except Exception as e:
        logger.warning(f"Error reading USV {usv_path}: {e}")
        return True

def find_unscraped_gm_list_tasks(campaign_name: str, limit: int = 50) -> None:
    campaign_node = paths.campaign(campaign_name)
    mission_path = campaign_node.path / "mission.usv"
    results_dir = campaign_node.path / "queues" / "gm-list" / "completed" / "results"
    output_path = campaign_node.path / "recovery" / "recovery_gm_list_tasks.txt"

    if not mission_path.exists():
        logger.error(f"Mission file not found: {mission_path}")
        return

    logger.info(f"Loading GM List mission from {mission_path}...")
    all_tasks: List[Any] = []
    with open(mission_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                parts = line.strip().split(UNIT_SEP)
                if len(parts) >= 4:
                    all_tasks.append({
                        "tile_id": parts[0],
                        "search_phrase": parts[1],
                        "latitude": float(parts[2]),
                        "longitude": float(parts[3])
                    })

    logger.info(f"Checking {len(all_tasks)} potential tasks for missing/hollow results...")
    
    unscraped: List[Any] = []
    for t in all_tasks:
        lat: float = t['latitude']
        lon: float = t['longitude']
        phrase: str = t['search_phrase']
        
        lat_shard = get_geo_shard(lat)
        grid_id = get_grid_tile_id(lat, lon)
        lat_tile, lon_tile = grid_id.split("_")
        phrase_slug = slugify(phrase)
        
        # Canonical Path: results/{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}.usv
        res_file = results_dir / lat_shard / lat_tile / lon_tile / f"{phrase_slug}.usv"
        
        if is_hollow_usv(res_file):
            unscraped.append(t)
            if len(unscraped) >= limit:
                break

    if not unscraped:
        logger.warning("No unscraped or hollow GM List tasks found!")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for t in unscraped:
            # We must use the correctly calculated grid_id to ensure conforming paths
            grid_id = get_grid_tile_id(t['latitude'], t['longitude'])
            f.write(f"{t['latitude']}|{t['longitude']}|{t['search_phrase']}|{grid_id}\n")
            
    logger.info(f"Successfully identified {len(unscraped)} tasks for re-enqueue.")
    logger.info(f"Target list: {output_path}")

if __name__ == "__main__":
    find_unscraped_gm_list_tasks("roadmap")
