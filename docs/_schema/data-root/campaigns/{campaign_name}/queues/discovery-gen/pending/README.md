# Discovery-Gen Pending Area

This directory holds work that has been defined but not yet activated for workers.

## `frontier.usv`
The "Next Up" list. This file is regenerated every time `prepare-mission` is run. It contains all rows from the master `mission.usv` that do not have a corresponding result in the global `scraped-tiles` index.

## `batches/`
Subsets of the frontier used for controlled execution.
- **Canary Batches**: Small lists (e.g., 50 items) used to verify code changes on a single node before scaling.
- **Recovery Batches**: Focused lists generated to fill gaps found during audits.

## Syntax
All files in this directory follow the `MissionTask` USV format:
`tile_id`␟`search_phrase`␟`latitude`␟`longitude`
