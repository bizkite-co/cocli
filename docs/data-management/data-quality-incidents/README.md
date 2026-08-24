# Data Quality Incidents Registry

A dated record of confirmed data-loss/corruption mechanisms in the prospect
pipeline: what broke, which model/fields it touched, how long it was live,
and whether the damage is recoverable.

## Why this exists

Audits, exports, and backfills all ask some version of "why is this field
missing?" Without a record of *known, already-diagnosed* gaps, every one of
those investigations re-derives the same history from scratch - which is
expensive (see the 2026-08-22/23 session that produced this registry: single
investigation, ~6 hours, rediscovered mechanisms that were each individually
non-obvious). A dated incident here lets that same question be answered in
one read: "yes, this is known, here's why, here's whether it can still be
fixed" - instead of another multi-hour investigation.

This is documentation, not tooling. Nothing currently consumes it
automatically. Each entry carries structured YAML frontmatter (model(s),
field(s), date range, pipeline stage, status, fix commit, per-campaign
recovery state) specifically so a future scanner/sorter can be built
without a docs rewrite once there are enough entries to need one - see the
template below for the exact fields. Wire it into `cocli audit` or the
export pipeline only once there's a concrete query to ask against it (e.g.
"suppress this field's absence in reports for rows whose `updated_at`
falls inside a known-bad window") - don't build the consumer speculatively;
the frontmatter is what makes building it later a parsing exercise, not
another rewrite.

## How to use this when investigating a gap

1. Check whether the affected model + field + date range below already
   explains it. If so, the gap is known and (per that incident's status)
   either permanently unrecoverable or fixable via a documented backfill.
2. If it doesn't match anything here, it's a new incident - investigate,
   fix, and add an entry per the template below before considering the
   investigation closed.

## Index

| # | Incident | Model | Fields | Date range live | Pipeline stage | Status |
|---|---|---|---|---|---|---|
| 1 | [Quote-character silent row drop in compaction](./001-quote-character-compaction-row-drop.md) | `GoogleMapsProspect`, `EmailEntry` | whole row (any field) | Pipeline inception → 2026-08-23 | `IndexService.compact()` fold (`_duckdb_fold_prospect_usv_files`); `EmailIndexManager.query()` | Fixed (turboship + roadmap deployed); whole-row loss backfillable only where an external snapshot exists (done for turboship's 20); residual field-level corruption cleaned on both campaigns via `cocli index clean-quote-corruption` |
| 2 | [CompanyName/CompanyAddress stripped legitimate apostrophes](./002-companyname-companyaddress-apostrophe-stripping.md) | `GoogleMapsProspect.name`, `.full_address`, `.street_address`; also `Company`, `Person` | `name`, `full_address`, `street_address` | 2026-07-04 → 2026-08-23 | Model validation (`CompanyName.validate()`, `CompanyAddress.validate()`) | Fixed; historical corruption cleaned on both turboship and roadmap checkpoints |
| 3 | [Whole-row LWW fold erased gm-list-only fields](./003-whole-row-lww-fold-field-erasure.md) | `GoogleMapsProspect` | `category`, `first_category`, any gm-list-only field | Pipeline inception → 2026-08-04 | `IndexService.compact()` fold (pre-`76666046` whole-row `ROW_NUMBER()` pick) | Fixed 2026-08-04; historical erasure permanent unless the original gm-list source file still exists on disk/S3 |

## Template for a new entry

Frontmatter fields, exactly as named (keep types consistent so a future
scanner doesn't have to special-case entries):

- `id`: three-digit string, e.g. `"004"` - matches the filename prefix
- `title`: same as the H1, kept in sync manually
- `models`: YAML list of model class names, e.g. `[GoogleMapsProspect]`
- `fields`: YAML list of field names, or `["*"]` for whole-row loss
- `pipeline_stage`: one-line string identifying the exact function/command
- `date_start`: ISO date, or the literal string `pipeline-inception` if unknown
- `date_end`: ISO date the fix landed, or `null` if still open
- `status`: one of `fixed`, `open`, `partial`
- `fix_commit`: short SHA, or `null` if still open
- `campaigns`: mapping of campaign name -> one of `cleaned`, `not-measured`,
  `partial (<why>)`, or `not-applicable`

```markdown
---
id: "NNN"
title: <short title>
models: [ModelName]
fields: [field_one, field_two]
pipeline_stage: "<exact function or command>"
date_start: <ISO date or pipeline-inception>
date_end: <ISO date or null>
status: fixed
fix_commit: <sha or null>
campaigns:
  turboship: cleaned
  roadmap: not-measured
---

# NNN: <short title>

- **Model(s):** 
- **Field(s) affected:** 
- **Date range live:** <first bad commit/date> → <fix commit/date, or "still open">
- **Pipeline stage / queue:** <exact function or command>
- **Discovered:** <date, and what prompted the investigation>

## Mechanism

<the actual causal chain, in enough detail that a future reader doesn't
need to re-derive it - include the specific code path and why it produced
the observed symptom>

## Evidence

<how it was confirmed - specific commands, specific place_ids/records,
specific before/after counts. Reasoning without a measurement doesn't
belong here.>

## Fix

<commit SHA(s), what changed>

## Recovery status

<can historical damage be backfilled? From what source? Is it complete,
partial, or permanently lost? Any known follow-up needed (e.g. "same fix
needs deploying to campaign X")>
```
