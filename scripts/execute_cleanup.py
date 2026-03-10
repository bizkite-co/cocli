import sys
import subprocess
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any, cast

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.paths import paths

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("cleanup_executor")

def get_nodes() -> List[Dict[str, Any]]:
    config_path = paths.root / "config" / "cocli_config.toml"
    if not config_path.exists():
        return []
    import tomli
    with open(config_path, "rb") as f:
        config = tomli.load(f)
    return cast(List[Dict[str, Any]], config.get("cluster", {}).get("nodes", []))

def remove_from_s3(file_list: List[str], campaign: str) -> None:
    """
    Removes the identified files from S3 using xargs for parallel execution.
    """
    logger.info("--- Removing stale files from S3 (Parallel) ---")
    local_data_root = str(paths.root)
    bucket_name = "roadmap-cocli-data-use1" 
    
    keys = []
    for file_path in file_list:
        if local_data_root in file_path:
            keys.append(f"s3://{bucket_name}/" + file_path.replace(local_data_root + "/", ""))

    if not keys:
        return

    # Use xargs to parallelize removal (10 at a time)
    temp_list = Path("temp/s3_remove_list.txt")
    with open(temp_list, "w") as f:
        for k in keys:
            f.write(f"{k}\n")
    
    cmd = f"cat {temp_list} | xargs -n 1 -P 10 aws s3 rm --recursive"
    try:
        subprocess.run(cmd, shell=True, check=True)
    except Exception as e:
        logger.error(f"Batch S3 removal failed: {e}")
    finally:
        if temp_list.exists():
            temp_list.unlink()

def remove_from_cluster(file_list: List[str]) -> None:
    """
    Removes the identified files or directories from each PI using combined SSH commands.
    """
    nodes = get_nodes()
    if not nodes:
        return

    local_data_root = str(paths.root)
    
    for node in nodes:
        host = node['host']
        if host == "octoprint.pi":
            continue
        
        logger.info(f"--- Cleaning {host} (Batch) ---")
        rel_paths = []
        for file_path in file_list:
            if local_data_root in file_path:
                rel_paths.append("~/.local/share/cocli_data/" + file_path.replace(local_data_root + "/", ""))
        
        if not rel_paths:
            continue

        # Split into chunks of 100 to avoid ARG_MAX issues
        chunk_size = 100
        for i in range(0, len(rel_paths), chunk_size):
            chunk = rel_paths[i:i + chunk_size]
            # Use rm -rf to handle directories identified in the report
            cmd = ["ssh", f"mstouffer@{host}", f"rm -rf {' '.join(chunk)}"]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except Exception as e:
                logger.error(f"Remote batch removal failed on {host}: {e}")

def remove_local(file_list: List[str]) -> None:
    """
    Removes files or directories from the local filesystem.
    """
    logger.info("--- Removing local stale items ---")
    for file_path in file_list:
        try:
            p = Path(file_path)
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        except Exception as e:
            logger.error(f"Local removal failed for {file_path}: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Execute removal of identified stale items.")
    parser.add_argument("--report", required=True, help="Path to the cleanup report file")
    parser.add_argument("--campaign", default="roadmap")
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()

    if not Path(args.report).exists():
        logger.error(f"Report not found: {args.report}")
        sys.exit(1)

    with open(args.report, "r") as f:
        to_remove = [line.strip() for line in f if line.strip()]

    logger.info(f"Loaded {len(to_remove)} items for removal.")
    
    # 1. Execute S3 Removal (Authority)
    if not args.local_only:
        remove_from_s3(to_remove, args.campaign)
        remove_from_cluster(to_remove)
    
    # 2. Execute Local Removal
    remove_local(to_remove)
    
    logger.info("Cleanup complete.")
