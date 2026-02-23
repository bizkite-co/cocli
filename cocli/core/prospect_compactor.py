# POLICY: frictionless-data-policy-enforcement
import logging
import shutil
from pathlib import Path
from typing import Set
from cocli.core.config import get_campaigns_dir
from cocli.core.sharding import get_grid_tile_id, get_geo_shard
from cocli.core.utils import UNIT_SEP
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
                        shutil.move(str(file_path), str(target_path))
                    else:
                        file_path.unlink()
                merged_count += 1
        except ValueError:
            continue

    _cleanup_empty_dirs(results_dir)
    return merged_count

def compact_prospects_to_checkpoint(campaign_name: str) -> int:
    """Merges all consolidated queue results into the main campaign checkpoint."""
    from cocli.core.paths import paths
    results_dir = paths.campaign(campaign_name).path / "queues" / "gm-list" / "completed" / "results"
    
    added = 0
    if not results_dir.exists():
        return 0

    for usv_file in results_dir.rglob("*.usv"):
        try:
            with open(usv_file, "r") as f:
                for line in f:
                    if line.strip():
                        prospect = GoogleMapsProspect.from_usv(line)
                        if prospect:
                            GoogleMapsProspect.append_to_checkpoint(campaign_name, prospect)
                            added += 1
            # Surgical cleanup: delete file after successful merge
            usv_file.unlink()
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
    src.unlink()

def _cleanup_empty_dirs(root: Path) -> None:
    dirs = sorted([d for d in root.rglob("*") if d.is_dir()], key=lambda x: len(x.parts), reverse=True)
    for d in dirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass
