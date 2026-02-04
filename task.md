# Task: Roadmap Campaign Identity Recovery & Shielding

## Objective
Recover 9,605 unique hollow roadmap records and enforce a "Model-to-Model" architecture to permanently prevent incomplete data saves.

## Phase 2: Identification Shield & Validation (COMPLETE)
- [x] **Strict Identity Model**: Update `GoogleMapsProspect` to make `name`, `place_id`, `company_slug`, and `company_hash` **REQUIRED**.
- [x] **Model-to-Model Pipeline**: Implemented transformation flow: `ListItem` (Discovery) -> `Task` (Queue) -> `Prospect` (Index).
- [x] **Gold Standard Identity**: Implemented AWS IoT Core X.509 authentication with automatic token refresh in supervisor.
- [x] **Explicit S3 Namespace**: Defined and implemented `DataPaths.s3_*` methods to ensure deterministic pathing.
- [x] **Async Stability**: Wrapped synchronous queue polling in threads to prevent supervisor event-loop stalls.
- [x] **Test ID Verification**: Confirmed hydration of test ID `ChIJrWcEWr8B2YgR7Sw1Y_d7GUw` in S3 (Shard `W`).

## Phase 3: Recovery Execution (CURRENT)
- [ ] **Index Cleanup**: Mass-sideline existing hollow S3 USV index files (< 1.5KB) to clear the path for fresh scrapes.
- [ ] **Enqueuing**: Populate the `gm-details` queue with the ~9,359 remaining hollow Place IDs using `scripts/enqueue_hollow_recovery.py`.
- [ ] **Cluster Processing**: Monitor RPI nodes as they re-scrape metadata and populate the sharded index.
- [ ] **Verification**: Run a post-recovery audit to ensure hollow records are replaced by valid, hydrated USVs (> 2KB).

## Technical Standards
- **Model Architecture**: Prohibit model reuse across phases.
    - `GoogleMapsListItem`: Discovery results (`name`, `slug`, `place_id`).
    - `GmItemTask`: Worker instructions (S3 Queue).
    - `GoogleMapsProspect`: Final hydrated data (S3 Index).
- **Deduplication**: Use `place_id.usv` as the filename in the index to ensure one record per location.
- **Data Format**: USV with `\x1f` (Unit Separator). Handle internal newlines by ensuring the model captures them in specific fields.
- **Operational Safety (1-3-10 Rule)**:
    - 1 item: Local test.
    - 3 items: S3 pilot run.
    - 10 items: Small batch verification.
    - **NEVER** enqueue thousands without a successful 10-item pilot.
- **S3 Safety**: Always use `--dry-run` before `aws s3 rm` or `aws s3 mv` on large buckets.
- **Log Management**:
    - Use `timeout 10s` for SSH log tails.
    - Use `grep -E` to target specific IDs or patterns.
    - Use `tail -n 50` or `--tail 50` to limit initial context.
    - Use `sudo truncate -s 0 <path>` to clear bloated RPI container logs.