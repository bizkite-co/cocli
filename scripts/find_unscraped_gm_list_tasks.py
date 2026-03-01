# POLICY: frictionless-data-policy-enforcement
import json
import logging
from cocli.core.paths import paths
from cocli.core.text_utils import slugify

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("find_gm_list_tasks")

def find_unscraped_gm_list_tasks(campaign_name: str, limit: int = 5) -> None:
    campaign_node = paths.campaign(campaign_name)
    mission_path = campaign_node.path / "mission.json"
    results_dir = campaign_node.path / "queues" / "gm-list" / "completed" / "results"
    output_path = campaign_node.path / "recovery" / "recovery_gm_list_tasks.txt"

    if not mission_path.exists():
        logger.error(f"Mission file not found: {mission_path}")
        return

    logger.info(f"Loading GM List mission from {mission_path}...")
    with open(mission_path, "r") as f:
        all_tasks = json.load(f)

    logger.info(f"Checking {len(all_tasks)} potential GM List tasks against results...")
    
    unscraped = []
    for t in all_tasks:
        lat = t['latitude']
        lon = t['longitude']
        phrase = t['search_phrase']
        shard = str(int(lat) % 10)
        
        res_file = results_dir / shard / f"{lat:.1f}" / f"{lon:.1f}" / f"{slugify(phrase)}.usv"
        
        if not res_file.exists():
            unscraped.append(t)
            if len(unscraped) >= limit:
                break

    if not unscraped:
        logger.warning("No unscraped GM List tasks found!")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for t in unscraped:
            # Format: lat|lon|phrase|tile_id
            f.write(f"{t['latitude']}|{t['longitude']}|{t['search_phrase']}|{t['tile_id']}\n")
            
    logger.info(f"Successfully identified {len(unscraped)} unscraped GM List tasks.")
    logger.info(f"Target list: {output_path}")

if __name__ == "__main__":
    find_unscraped_gm_list_tasks("roadmap")
