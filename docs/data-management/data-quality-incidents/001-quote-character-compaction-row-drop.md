# 001: Quote-character silent row drop in compaction

- **Model(s):** `GoogleMapsProspect` (primary); `EmailEntry` via a related read path
- **Field(s) affected:** whole row - any field, not one column. The place_id
  disappears from the checkpoint entirely.
- **Date range live:** pipeline inception → 2026-08-23 (fixed)
- **Pipeline stage / queue:** `IndexService.compact()`'s DuckDB fold
  (`_duckdb_fold_prospect_usv_files` in `cocli/core/stations_runtime.py`),
  run by every `cocli index compact` and every `cocli web deploy`.
  Secondarily, `EmailIndexManager.query()`'s two `read_csv` calls (lookup/
  dedup path - not the email `compact()` write path, which uses a different,
  unaffected mechanism).
- **Discovered:** 2026-08-23, while investigating why a June 2026 export CSV
  (2,249 real companies with phone/email/category) had shrunk to 2,462
  overall yield with specific companies missing entirely, prompted directly
  by user pushback ("we have to find all the records that were in the 2510
  version and are not in the latest version and find out why").

## Mechanism

DuckDB's `read_csv()` defaults to `"` (double-quote) as its quote character.
`_duckdb_fold_prospect_usv_files` calls `read_csv(..., ignore_errors=True)`
without `quote=''`, so any USV field containing several literal `"`
characters in a row - a real, recurring scraper artifact (a mangled
`full_address` wrapped in a run of repeated `"` characters, e.g.
`"""""1501 Heritage Pkwy # 105"""""`) - breaks DuckDB's default quote
parsing for that row. Combined with `ignore_errors=True`, this doesn't just
corrupt the offending field - it drops the **entire row** from the query's
output, silently. `ignore_errors=True` swallows the parse failure with no
warning, and the fold's own success check
(`dest.exists() and dest.stat().st_size >= 0`) only verifies a destination
file was created, never that it has the expected row count. So a
compaction that quietly loses rows looks identical, from every log and
audit signal available, to one that succeeded normally.

This is strictly worse than incident 003 (whole-row LWW field erasure):
that one hollowed a column while keeping the row; this one deletes the
place_id from the checkpoint forever, with nothing left to grep for
afterward - the row is gone, not merely incomplete.

The export script (`scripts/export_enriched_emails.py`) already set
`quote=''` correctly on its own `read_csv` calls - it was the reference
that exposed what the fold and `EmailIndexManager.query()` were missing.

## Evidence

Isolated repro using a real checkpoint row's actual content (place_id
`ChIJ61JWq1sv9ocRwEjYlpERwKc`, "Pro Flooring Installers – Eagan"):
`read_csv` without `quote=''` produced **0** output rows for a 2-row input;
with `quote=''`, **2** rows (correctly LWW-folded to 1, preserving the
older row's `category` over the newer hollow write's blank one).

Cross-checked against the 20 companies confirmed missing entirely from the
checkpoint (present 2026-06-29, gone by 2026-08-14, confirmed via 6
historical checkpoint backups spanning that window): **all 20 of 20** had
heavy quote contamination in their June 29 row (30-124 literal `"`
characters each). Not circumstantial - every single missing company matched
the corruption pattern.

Broader checkpoint scan (16,777 rows, post-fix): **1,183 rows (7%)** had at
least one field with a literal `"` character, concentrated in
`street_address` (958) and `full_address` (744), with 197 in `name` (see
incident 002 for why most of those `name` hits were actually legitimate
apostrophes, not this bug).

## Fix

Commit `931cc4ec`. Added `quote=''` to both DuckDB `read_csv` call sites
that were missing it: the prospects fold, and `EmailIndexManager.query()`'s
two `read_csv` calls. Regression test added:
`test_prospects_compact_survives_literal_quote_characters_in_fields`
(`tests/unit/test_prospects_stations_compact.py`) - confirmed it fails
without the fix (0 output rows) before landing the change.

Deployed to both Pi worker nodes: `cocli5x0` (turboship, 2026-08-23) and
`cocli5x1` (roadmap, 2026-08-23) via `cocli cluster deploy-hotfix`.

## Recovery status

**Going forward: fully fixed.** No new rows will silently vanish from
compaction due to this mechanism on either campaign.

**Historical damage: partially recoverable, source-dependent.** A row lost
to this bug is gone from the checkpoint/WAL for good - there's nothing left
inside the pipeline to recover it from. Recovery is only possible if an
external snapshot predates the loss. For turboship, a June 2026 export CSV
snapshot existed and was used to restore the 20 confirmed-missing
companies (checkpoint 16,757 → 16,777 rows) plus backfill `category` on 109
further rows whose data survived in the checkpoint but had lost their
category - see the `backup/turboship-emails-june-2026.csv` file and the
one-off scripts referenced in this incident's investigation (not yet
promoted to a reusable `cocli` command - see incident-registry follow-up).

**Roadmap: not yet checked.** Roadmap's checkpoint isn't synced to the dev
machine, so it hasn't been scanned for the same corruption pattern or
whole-row losses. The fix is deployed there, but no historical audit or
cleanup has been run yet - this is an open follow-up.
