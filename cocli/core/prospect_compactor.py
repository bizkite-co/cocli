# POLICY: frictionless-data-policy-enforcement
import logging

logger = logging.getLogger(__name__)

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
