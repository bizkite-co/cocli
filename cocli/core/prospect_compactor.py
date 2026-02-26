# POLICY: frictionless-data-policy-enforcement
import logging
import shutil
from pathlib import Path
from typing import Set
from cocli.core.config import get_campaigns_dir
from cocli.core.sharding import get_grid_tile_id, get_geo_shard
from cocli.core.constants import UNIT_SEP
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

logger = logging.getLogger(__name__)

def consolidate_campaign_results(campaign_name: str) -> int:
    """Consolidates high-precision gm-list results into standardized 0.1-degree tiles."""
    campaign_dir = get_campaigns_dir() / campaign_name
    results_dir = campaign_dir / "queues" / "gm-list" / "completed" / "results"
    
    if not results_dir.exists():
        return 0

    all_files = list(results_dir.rglob("*.*"))
    merged_count = 0
    
    for file_path in all_files:
        rel_path = file_path.relative_to(results_dir)
        parts = rel_path.parts
        if len(parts) < 4: 
            continue
            
        lat_str, lon_str, filename = parts[1], parts[2], parts[3]
        
        try:
            lat, lon = float(lat_str), float(lon_str)
            is_standard = ('.' in lat_str and len(lat_str.split('.')[-1]) == 1) and \
                          ('.' in lon_str and len(lon_str.split('.')[-1]) == 1)
            
            if not is_standard:
                correct_tile = get_grid_tile_id(lat, lon)
                c_lat, c_lon = correct_tile.split("_")
                c_shard = get_geo_shard(lat)
                target_path = results_dir / c_shard / c_lat / c_lon / filename
                
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                if file_path.suffix.lower() == ".usv":
                    _merge_usv(file_path, target_path)
                else:
                    if not target_path.exists():
                        shutil.copy2(str(file_path), str(target_path))
                    # MANDATE: Never unlink the source trace file. 
                    # It must remain as a witness of the session.
                merged_count += 1
        except ValueError:
            continue

    _cleanup_empty_dirs(results_dir)
    return merged_count

def compact_prospects_to_checkpoint(campaign_name: str) -> int:
    """Merges all sharded WAL prospects into the main campaign checkpoint."""
    from cocli.core.paths import paths
    wal_dir = paths.campaign(campaign_name).index("google_maps_prospects").wal
    
    added = 0
    
    if not wal_dir.exists():
        logger.info("WAL directory does not exist. Nothing to compact.")
        return 0
            
    logger.info("Compacting prospects from wal...")
    
    # rglob to catch sharded subdirectories in WAL
    for usv_file in wal_dir.rglob("*.usv"):
        if usv_file.name == "prospects.checkpoint.usv":
            continue
            
        try:
            with open(usv_file, "r") as f:
                for line in f:
                    if line.strip():
                        # skip potential headers if they were missed by cleanup
                        if "created_at" in line or "scrape_date" in line:
                            continue
                        try:
                            prospect = GoogleMapsProspect.from_usv(line)
                            if prospect and prospect.place_id:
                                GoogleMapsProspect.append_to_checkpoint(campaign_name, prospect)
                                added += 1
                        except Exception as e:
                            logger.warning(f"Failed to parse prospect in {usv_file}: {e}")
            
            # Surgical cleanup: delete file after successful merge
            usv_file.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Failed to merge {usv_file}: {e}")
            
    return added

def _merge_usv(src: Path, dest: Path) -> None:
    existing_pids: Set[str] = set()
    if dest.exists():
        for line in dest.read_text().splitlines():
            if line.strip():
                existing_pids.add(line.split(UNIT_SEP)[0])

    new_rows = []
    for line in src.read_text().splitlines():
        if line.strip():
            pid = line.split(UNIT_SEP)[0]
            if pid not in existing_pids:
                new_rows.append(line)
                existing_pids.add(pid)
    
    if new_rows:
        with open(dest, "a", encoding="utf-8") as df:
            for row in new_rows:
                df.write(row + "\n")
    # MANDATE: Never unlink the source trace file.

def _cleanup_empty_dirs(root: Path) -> None:
    dirs = sorted([d for d in root.rglob("*") if d.is_dir()], key=lambda x: len(x.parts), reverse=True)
    for d in dirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass
