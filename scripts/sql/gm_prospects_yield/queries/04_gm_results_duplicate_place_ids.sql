-- Gate check before ever running compact_gm_list_results() again:
-- cocli/core/transformers/gm_list_to_checkpoint.py breaks ties on
-- COALESCE(cp.updated_at, gm.discovery_tile_id) DESC - but discovery_tile_id
-- is a tile-coordinate string like "34.1_-118.4_flooring-contractor", not a
-- timestamp. If a place_id has multiple gm_results rows, "newest wins" falls
-- back to sorting tile-id strings alphabetically, i.e. an arbitrary pick,
-- and the per-field COALESCE merge only sees whichever row won - not the
-- union of everything gm-list actually knows about that place. Do not run
-- the compactor while this returns rows with count > 1.
SELECT place_id, COUNT(*) AS n_rows
FROM gm_results
GROUP BY place_id
HAVING COUNT(*) > 1
ORDER BY n_rows DESC;
