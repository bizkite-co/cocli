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
    """
    Merges all sharded WAL prospects into the main campaign checkpoint using DuckDB.
    Performs a full deduplicated rewrite to eliminate bloat.
    """
    from cocli.core.paths import paths
    idx_paths = paths.campaign(campaign_name).index("google_maps_prospects")
    wal_dir = idx_paths.wal
    checkpoint_path = idx_paths.checkpoint
    
    if not wal_dir.exists():
        logger.info("WAL directory does not exist. Nothing to compact.")
        return 0
            
    logger.info("Compacting prospects with DuckDB deduplication...")
    
    import duckdb
    con = duckdb.connect(database=':memory:')
    
    # 1. Collect all sources (Checkpoint + all WAL files)
    sources = []
    if checkpoint_path.exists() and checkpoint_path.stat().st_size > 0:
        sources.append(str(checkpoint_path))
    
    for usv_file in wal_dir.rglob("*.usv"):
        if usv_file.is_file() and usv_file.stat().st_size > 0:
            sources.append(str(usv_file))
            
    if not sources:
        return 0

    try:
        # Create a combined view using read_csv on all paths
        # column00: place_id, column05: updated_at (for sorting)
        source_list_str = ", ".join([f"'{s}'" for s in sources])
        
        # Deduplication Strategy: Select the record with the newest updated_at for each place_id
        # We use all_varchar=True to avoid parsing errors during the massive merge
        con.execute(f"""
            CREATE TABLE deduplicated_prospects AS
            SELECT * FROM (
                SELECT *, 
                       row_number() OVER (PARTITION BY column00 ORDER BY column05 DESC) as rn
                FROM read_csv([{source_list_str}], delim='\x1f', header=False, auto_detect=True, all_varchar=True)
                WHERE column00 IS NOT NULL AND column00 LIKE 'ChIJ%'
            ) WHERE rn = 1
        """)
        
        # 2. Write the clean checkpoint to a temporary file
        temp_checkpoint = checkpoint_path.with_suffix(".tmp.usv")
        con.execute(f"COPY (SELECT * EXCLUDE (rn) FROM deduplicated_prospects) TO '{temp_checkpoint}' (DELIMITER '\x1f', HEADER FALSE)")
        
        # 3. Swap and Cleanup
        new_count = con.execute("SELECT COUNT(*) FROM deduplicated_prospects").fetchone()[0]
        
        # Replace old checkpoint
        if temp_checkpoint.exists():
            temp_checkpoint.replace(checkpoint_path)
            
        # Clear WAL files that were merged
        for usv_file in wal_dir.rglob("*.usv"):
            if usv_file.is_file():
                usv_file.unlink()
                
        logger.info(f"Compaction successful. New unique prospects: {new_count}")
        return int(new_count)

    except Exception as e:
        logger.error(f"DuckDB Compaction failed: {e}")
        return 0

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
