# GmListResult Data Recovery Runbook

This runbook outlines the steps to recover and integrate GmListResult data into the primary prospects checkpoint.

## Prerequisites
- A running development or production environment.
- Access to the raw GmListResult files (`queues/gm-list/completed/results/`).
- `corrupted-records.usv` (if restoring original corrupted data).

## Step-by-Step Recovery

### 1. Stop Data Pipelines
Stop all active scrapers, enrichers, or workers to prevent data race conditions or incoming data influx during the repair.

### 2. Restore Corrupted Records
If files are corrupted (e.g., embedded newlines), restore them using the provided utility:
```bash
python3 scripts/restore_gm_list_results.py
```
This utility processes `corrupted-records.usv` and restores valid records.

### 3. Clean Source Data
Clean the source USV files to ensure schema consistency (9 fields, starts with 'ChI'):
```bash
python3 scripts/clean_and_analyze_gm_list.py
```
*Note: This script iterates through `queues/gm-list/completed/results/**/*.usv` and overwrites files with cleaned content.*

### 4. Compact Data into Checkpoint
Run the transformer to merge the cleaned source data into the main prospects checkpoint (`prospects.checkpoint.usv`):
```bash
python3 -c "from cocli.core.transformers.gm_list_to_checkpoint import compact_gm_list_results; compact_gm_list_results('YOUR_CAMPAIGN_NAME')"
```
*This utility deduplicates records based on `place_id` and ensures column-order consistency.*

### 5. Verification
Verify the checkpoint record count:
```bash
wc -l ~/.local/share/cocli_data/campaigns/YOUR_CAMPAIGN_NAME/indexes/google_maps_prospects/prospects.checkpoint.usv
```
*(Ensure the count aligns with expected results after deduplication)*

### 6. Restart Data Pipelines
Resume all stopped scrapers, enrichers, and workers.
