# Task: Roadmap Campaign Data Migration & Identity Restoration

## Objective
Standardize the `roadmap` campaign data to the new USV architecture and recover any metadata lost during the "Silent Hollow Save" incident (documented in [docs/issues/hollow-data-dislocation.md](docs/issues/hollow-data-dislocation.md)).

## Context & Current State
- **Campaign**: `roadmap`
- **Bucket**: `s3://roadmap-cocli-data-use1/`
- **AWS Profile**: `westmonroe-support`
- **Data Integrity**: 
    - The `roadmap` data is in a "Partially Dislocated" state. Place IDs and websites are intact, but key metadata (Name, City, Zip) is missing in several records.
    - Legacy headers (PascalCase) are still present in S3 USV files.
- **Worker Status**: 
    - Raspberry Pi workers (`cocli5x0`, `coclipi`, `octoprint`) were running v0.2.89 (buggy models).
    - **CRITICAL**: Workers have been remotely "paused" by setting scaling to 0 in `config.toml`. Do not resume until they are updated to v0.26.0+.
- **Queue System**: 
    - Campaign uses **Distributed Filesystem Queue (DFQ)** based in S3 (`campaigns/roadmap/queues/`).
    - Legacy SQS queues should be decommissioned after migration.

## Technical Standards (The "Shield")
- **Field Separator**: `\x1f` (Unit Separator)
- **Record Separator**: `\n` (Standard Newline)
- **DuckDB Integration**: Queries must surgically strip legacy `\x1e` (CHR 30) characters:
  ```sql
  SELECT trim(replace(col, CHR(30), '')) FROM read_csv(...) 
  ```
- **Mandatory Identifiers**: `place_id` (Type: `PlaceID`) is non-optional. The "Identity Tripod" (8-8-5 Hash) is used for secondary linking.

## Safety Protocol (The "1-3-10" Rule)
1. **READ-ONLY First**: Perform extensive `aws s3 ls` and `cat -A` investigations before writing any migration scripts.
2. **Sampling**: When attempting a migration or repair, run it on a small sample first:
    - Test on **1** record.
    - Test on **3** records.
    - Test on **10** records.
3. **Dry Runs**: All migration scripts **MUST** implement a `--dry-run` flag to review the transformed data in the console before applying it to S3.

## Immediate Next Steps
1.  **Audit Identity Gap**: Run an audit on `roadmap` prospects to count how many records are "hollow" (missing Name/City).
2.  **Verify Linkage**: Check if the missing metadata exists in the `companies/` markdown files in the `roadmap` bucket.
3.  **Heal Shards**: Implement a healing process using the sampling rule above to restore metadata from companies/markdown to the prospect index.
4.  **Standardize Formats**: Migrate legacy `\x1e` files to the clean `\n` newline standard.
