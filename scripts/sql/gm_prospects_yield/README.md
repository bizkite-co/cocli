# gm-list -> gm-details -> checkpoint -> export yield diagnostics

Read-only DuckDB queries for tracing where the Google Maps Prospects export
count leaks, relative to the checkpoint and gm-list source data. Built so
each question is a standalone, re-runnable `.sql` file instead of a one-off
Python heredoc that gets thrown away after one investigation.

## Usage

```bash
uv run python scripts/sql/gm_prospects_yield/build_db.py turboship
# build_db.py prints the exact db path it wrote (under
# $COCLI_DATA_HOME/campaigns/<campaign>/_diagnostics/gm_prospects_yield.duckdb)
duckdb "$COCLI_DATA_HOME/campaigns/turboship/_diagnostics/gm_prospects_yield.duckdb" \
    < scripts/sql/gm_prospects_yield/queries/01_checkpoint_field_coverage.sql
```

`build_db.py` materializes `prospects` (checkpoint), `gm_results` (gm-list
completed results), and `emails` (sharded email index) into a persisted
`.duckdb` file under `<campaign>/_diagnostics/` (covered by the repo-root
`/data` gitignore - not committed). Re-run it any time to refresh against
current data; it never writes to the checkpoint, WAL, or gm-list queue.

## Queries

- `01_checkpoint_field_coverage.sql` - overall null-rate on phone/domain/category.
- `02_category_coverage_by_write_day.sql` - category coverage clustered by
  `updated_at` day, to spot "field was never written before date X" patterns
  (not just per-row merge bugs).
- `03_export_yield_funnel.sql` - mirrors `scripts/export_enriched_emails.py`'s
  join + HAVING + category-gate chain as a funnel. Lower bound only - doesn't
  replicate the per-company `website.md` found_keywords rescue.
- `04_gm_results_duplicate_place_ids.sql` - **run before ever re-running
  `compact_gm_list_results()`**. If this returns rows, that tool's LWW
  tiebreak (`COALESCE(cp.updated_at, gm.discovery_tile_id) DESC`) picks an
  arbitrary gm-list row per place_id, not the richest one.
- `05_rescuable_missing_category.sql` - of the checkpoint rows missing
  category, how many gm-list already has locally vs. how many need a
  different source entirely.

Add a new `.sql` file per new question rather than writing another disposable
Python script - that's the whole point of this directory.
