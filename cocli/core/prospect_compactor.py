# POLICY: frictionless-data-policy-enforcement
import logging
import shutil
from pathlib import Path
from typing import Set
from cocli.core.config import get_campaigns_dir
from cocli.core.sharding import get_grid_tile_id, get_geo_shard
from cocli.core.constants import UNIT_SEP

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
                merged_count += 1
        except ValueError:
            continue

    _cleanup_empty_dirs(results_dir)
    return merged_count

def compact_prospects_to_checkpoint(campaign_name: str) -> int:
    """
    UNIFIED ENGINE: Merges sharded WAL prospects and/or sorts/dedupes the main checkpoint.
    This is the SINGLE SOURCE OF TRUTH for index stability.
    """
    from cocli.core.paths import paths
    idx_paths = paths.campaign(campaign_name).index("google_maps_prospects")
    wal_dir = idx_paths.wal
    checkpoint_path = idx_paths.checkpoint
    
    logger.info(f"--- Index Compaction Engine: {campaign_name} ---")
    
    import duckdb
    con = duckdb.connect(database=':memory:')
    
    try:
        # 1. Collect all sources
        sources = []
        if checkpoint_path.exists() and checkpoint_path.stat().st_size > 0:
            sources.append(str(checkpoint_path))
        
        if wal_dir.exists():
            for usv_file in wal_dir.rglob("*.usv"):
                if usv_file.is_file() and usv_file.stat().st_size > 0:
                    sources.append(str(usv_file))
                
        if not sources:
            logger.info("No data sources found for compaction.")
            return 0

        # 2. Define schema (56 columns for GoogleMapsProspect)
        columns_def = {f"column{i:02d}": "VARCHAR" for i in range(56)}
        columns_str = ", ".join([f"'{k}': '{v}'" for k, v in columns_def.items()])
        source_list_str = ", ".join([f"'{s}'" for s in sources])

        # 3. Deduplicate and Sort
        # Strategy: Keep newest record (column05) and sort alphabetically by Place ID (column00)
        con.execute(f"""
            CREATE TABLE deduplicated_prospects AS
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, 
                       row_number() OVER (PARTITION BY column00 ORDER BY column05 DESC) as rn
                FROM read_csv([{source_list_str}], delim='\x1f', header=False, auto_detect=False, 
                              all_varchar=True, columns={{{columns_str}}}, quote='', null_padding=True)
                WHERE column00 IS NOT NULL AND column00 LIKE 'ChIJ%'
            ) WHERE rn = 1
            ORDER BY column00 ASC
        """)
        
        # 4. Atomic Write
        temp_checkpoint = checkpoint_path.with_suffix(".tmp.usv")
        con.execute(f"COPY deduplicated_prospects TO '{temp_checkpoint}' (DELIMITER '\x1f', HEADER FALSE)")
        
        # 5. Verify and Swap
        res = con.execute("SELECT COUNT(*) FROM deduplicated_prospects").fetchone()
        new_count = res[0] if res else 0
        
        if temp_checkpoint.exists():
            temp_checkpoint.replace(checkpoint_path)
            
            # 6. Cleanup WAL files only after successful swap
            if wal_dir.exists():
                for usv_file in wal_dir.rglob("*.usv"):
                    if usv_file.is_file():
                        usv_file.unlink()
                
            logger.info(f"Compaction successful. Final unique prospects: {new_count}")
            return int(new_count)
        else:
            logger.error("Failed to generate compacted output.")
            return 0

    except Exception as e:
        logger.error(f"Compaction failed: {e}")
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

def _cleanup_empty_dirs(root: Path) -> None:
    dirs = sorted([d for d in root.rglob("*") if d.is_dir()], key=lambda x: len(x.parts), reverse=True)
    for d in dirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass
