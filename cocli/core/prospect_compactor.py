# POLICY: frictionless-data-policy-enforcement
import logging

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

logger = logging.getLogger(__name__)

# Column count MUST come from the model, never a hardcoded number - the
# model's own docstring already mandates this ("Do not maintain a
# parallel column list in compact"). Found violated 2026-08-27: a
# hardcoded 56 (from when the model had 56 fields) silently broke
# compaction entirely once a 57th field (category) was added - real
# turboship data now has a mix of 56- and 57-column rows, and DuckDB's
# strict-mode CSV reader rejects any row with MORE columns than declared
# (null_padding only helps rows with FEWER). This wasn't a false alarm:
# compact_prospects_to_checkpoint() was silently returning 0 against the
# live checkpoint (caught, logged, swallowed by the try/except) before
# this fix - confirmed by running the pre-fix code against the same file.
_PROSPECT_COLUMN_COUNT = len(GoogleMapsProspect.usv_field_names())

# Columns (0-indexed, matching GoogleMapsProspect.model_fields order) that
# describe THIS SPECIFIC WRITE/ATTEMPT rather than accumulated knowledge
# about the business - these always take the winning (latest by
# updated_at) row's own value verbatim, never falling back to an older
# row's value even if the latest is "hollow" for that column. Mirrors
# _WEBSITE_NEVER_MERGE_FROM_EXISTING's rationale in
# cocli/models/companies/website.py. updated_at (5) doubles as the
# tie-breaker/ordering key itself, so it can never be a merge candidate.
_PROSPECT_NEVER_MERGE_COLUMN_INDICES = {
    4,   # created_at
    5,   # updated_at
    6,   # version
    7,   # processed_by
    8,   # company_hash
    52,  # uuid
}


def compact_prospects_to_checkpoint(campaign_name: str) -> int:
    """
    UNIFIED ENGINE: Merges sharded WAL prospects and/or sorts/dedupes the main checkpoint.
    This is the SINGLE SOURCE OF TRUTH for index stability.

    Per-field hollow-aware merge (not pure last-write-wins): for each
    place_id, each merge-eligible column independently prefers the most
    recent NON-HOLLOW value across all candidate rows, falling back to an
    older row's value when the latest row is hollow for that field
    specifically. A later gm-details rescrape that finds the place but
    fails to extract rating/hours/website no longer silently discards an
    earlier, richer record for those fields - it only overwrites what it
    actually found something new for. See task-agent ticket
    per-field-hollow-check-merge-safety-for-gm-details-prospects-index-compaction.
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

        # 2. Define schema (column count derived from the model - see
        # _PROSPECT_COLUMN_COUNT)
        columns_def = {f"column{i:02d}": "VARCHAR" for i in range(_PROSPECT_COLUMN_COUNT)}
        columns_str = ", ".join([f"'{k}': '{v}'" for k, v in columns_def.items()])
        source_list_str = ", ".join([f"'{s}'" for s in sources])

        # 3. Deduplicate and Sort, per-field hollow-aware
        # For each place_id (column00) and each merge-eligible column,
        # FIRST_VALUE picks the value from the row that sorts first under
        # "non-hollow before hollow, then most-recent-updated_at first" -
        # so an older row's non-empty value survives a newer row that's
        # empty for that one column. Never-merge columns (see set above)
        # just take the winning row's own value (ORDER BY updated_at DESC
        # alone, no hollow preference). All FIRST_VALUE window functions
        # below share one PARTITION BY/frame and evaluate independently
        # per row - row_number() then collapses each place_id's now
        # per-column-merged duplicate rows down to one.
        column_exprs = []
        for i in range(_PROSPECT_COLUMN_COUNT):
            col = f"column{i:02d}"
            if i in _PROSPECT_NEVER_MERGE_COLUMN_INDICES:
                order_by = "column05 DESC"
            else:
                order_by = f"({col} IS NULL OR {col} = '') ASC, column05 DESC"
            column_exprs.append(
                f"FIRST_VALUE({col}) OVER (PARTITION BY column00 ORDER BY {order_by} "
                f"ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS {col}"
            )
        columns_select = ",\n                       ".join(column_exprs)

        con.execute(f"""
            CREATE TABLE deduplicated_prospects AS
            SELECT * EXCLUDE (rn) FROM (
                SELECT {columns_select},
                       row_number() OVER (PARTITION BY column00 ORDER BY column05 DESC) as rn
                FROM read_csv([{source_list_str}], delim='\x1f', header=False, auto_detect=False,
                              all_varchar=True, columns={{{columns_str}}}, quote='', null_padding=True)
                WHERE column00 IS NOT NULL AND column00 LIKE 'ChIJ%'
            ) WHERE rn = 1
            ORDER BY column00 ASC
        """)
        
        # 4. Atomic Write
        temp_checkpoint = checkpoint_path.with_suffix(".tmp.usv")
        from cocli.utils.duckdb_utils import USV_COPY_OPTIONS

        con.execute(
            f"COPY deduplicated_prospects TO '{temp_checkpoint}' ({USV_COPY_OPTIONS})"
        )
        
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
