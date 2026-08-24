---
id: "003"
title: Whole-row LWW fold erased gm-list-only fields
models: [GoogleMapsProspect]
fields: [category, first_category]
pipeline_stage: "IndexService.compact() fold (pre-76666046 whole-row ROW_NUMBER() pick)"
date_start: pipeline-inception
date_end: "2026-08-04"
status: fixed
fix_commit: "76666046"
campaigns:
  turboship: partial (recoverable only where gm-list source file still exists)
  roadmap: not-measured
---

# 003: Whole-row LWW fold erased gm-list-only fields

- **Model(s):** `GoogleMapsProspect`
- **Field(s) affected:** `category`, `first_category`, and any other field
  only ever populated by gm-list's search-result context (gm-details' own
  detail-page scrape never captures category at all - it only ever refreshes
  phone/hours/address-type fields).
- **Date range live:** pipeline inception → 2026-08-04 (fixed, commit
  `76666046`)
- **Pipeline stage / queue:** `IndexService.compact()`'s DuckDB fold
  (`_duckdb_fold_prospect_usv_files` in `cocli/core/stations_runtime.py`) -
  same function as incident 001, different bug in the same code.
- **Discovered:** originally task-agent ticket `recover-dropped-fields`
  (pre-dates this session). Re-confirmed 2026-08-23 while explaining to the
  user why a June 2026 export snapshot had higher category coverage (1,842
  of 2,249 companies, 82%) than the current checkpoint.

## Mechanism

Before the fix, the fold picked an entire row via
`ROW_NUMBER() OVER (PARTITION BY place_id ORDER BY updated_at DESC) WHERE
row_num = 1` - whichever source row for a place_id had the latest
`updated_at` won *all* of its columns, including columns that writer never
touched. In this pipeline every WAL entry is a **partial** write: gm-list
captures category/address from search-result context, gm-details later
re-scrapes phone/hours from the detail page (never category), enrichment
adds email. So any time a gm-details or enrichment write for a place_id
was more recent than the gm-list write that had originally captured its
category, the whole-row pick discarded the gm-list row entirely - erasing
category permanently, even though the newer row never claimed to know
anything about category one way or the other. This ran on every
compaction cycle for the pipeline's full history before the fix landed.

## Evidence

Historical: this session's earlier investigation (predates the writing of
this registry) measured that after the fix, only ~3.9% of currently
cross-referenceable rows still showed a category drop, confirming the fix
stopped active erosion.

Re-confirmed 2026-08-23: spot-checked "Above All Flooring"
(`ChIJBxVaxz8-9ocRPc9ClwIdiqQ`) - its checkpoint row's `created_at` exactly
equals its `updated_at` (`2026-06-27T05:54:42`, to the microsecond),
meaning the row has never been touched since its original gm-details
write - it never had a category from gm-details in the first place. Its
June 2026 export category ("Flooring contractor") had to have come from a
gm-list result file that no longer exists locally on disk (confirmed via
direct search - no matching gm-list result, no matching WAL entry).
Broader check against the 124 June companies still present in the
checkpoint but missing from the current export: 102 of 124 (82%) fit this
exact shape - email still resolves fine via the domain index, category is
just genuinely absent from the checkpoint, consistent with pre-fix erasure
whose only surviving copy (the gm-list source file) has since rotated out
of local storage.

## Fix

Commit `76666046` (2026-08-04, predates this session). Replaced the
whole-row `ROW_NUMBER()` pick with a per-column
`arg_max(col, key) FILTER (WHERE col has a real value)` - each column
independently keeps the most recent row that actually populated it, so a
later gm-details write with no category can no longer overwrite an earlier
gm-list write's real category.

Separately, `compact_gm_list_results()` (`cocli/core/transformers/
gm_list_to_checkpoint.py`) - a `COALESCE(gm_list.field, checkpoint.field)`
merge that recovers gm-list category data back into the checkpoint - existed
since 2026-06-29 but was never wired into the automatic compaction cycle
until commit `a03fc2d0` (2026-08-22, this session), closing a related
automation gap (not itself a data-loss bug, but the reason the fix's
recovery mechanism wasn't running by default).

## Recovery status

**Going forward: fully fixed** as of 2026-08-04. Category and other
gm-list-only fields no longer get silently erased by newer partial writes.

**Historical damage: permanent unless the original gm-list source file
still exists.** `compact_gm_list_results()` can recover a lost category
only for place_ids whose gm-list result file is still present on local
disk (confirmed during this session's standalone recovery run: only ~36%
of the checkpoint had a currently-present gm-list source, yielding +223
recovered rows). For place_ids whose source has already rotated out (the
"Above All Flooring" case above, and the majority of the 102-of-124
pattern), the category is gone for good unless recovered from an
independent external snapshot the way incident 001's June-CSV backfill did
- there is no internal mechanism left to reconstruct it.

**Roadmap:** not separately audited for this incident's category-erosion
rate - `compact_gm_list_results()`'s automation-gap fix (`a03fc2d0`) applies
to both campaigns equally since it's shared code, but roadmap's actual
recovery yield (how much of its checkpoint still has a recoverable gm-list
source) hasn't been measured.
