# Task: TUI Parity & Enrichment Pipeline Stabilization

## Objective
Achieve full feature and data parity in the TUI while stabilizing the automated enrichment pipeline to ensure all 29k+ prospects are processed.

## Phase 3: TUI/CLI Parity (Active)
### Feature Gaps
- [ ] **Contact Management**: Implement full menu for adding (new/existing), editing, and deleting contacts (currently placeholders).
- [ ] **Add Meeting**: Implement the `a` action for meetings (currently "coming soon").
- [ ] **Meeting Management**: Add ability to open meeting files in the editor (`m`).
- [ ] **Tag Management**: Add `t` and `T` bindings for adding and removing company tags.
- [ ] **Exclude Company**: Implement the `X` binding to add companies to the exclusion list.
- [ ] **Re-enrichment**: Add `r` binding to update domain and trigger re-enrichment.
- [ ] **Enhanced Call**: Update `p` binding to automatically create a meeting entry after the call (CLI parity).
- [ ] **Multi-line Notes**: Add a full-screen `TextArea` editor for the Notes quadrant.

### Data Gaps
- [ ] **Company Markdown**: Display the body text/content of the company's `_index.md`.
- [ ] **Extended Metadata**: Show 'Type', 'Services', 'Products', 'Tech Stack', 'Visits per day', 'Timezone'.
- [ ] **Contact Details**: Show phone numbers in the contacts table.
- [ ] **Meeting Precision**: Show full datetime for meetings instead of just the date.
- [ ] **Note Titles**: Include titles in the notes preview list.

## Phase 4: Person Parity
- [ ] **UI Alignment**: Update Person Detail view to match the 2x2 grid structure.
- [ ] **Inline Edits**: Enable inline editing for all Person fields.

## Phase 5: Unified Management Hub & Navigation Hierarchy (COMPLETED)
### Navigation Refinement
- [x] **Contextual "Drill-Up"**: Unified `alt+s`, `escape`, and `ctrl+c` to move exactly one level up the tree (Field -> Table -> Panel -> List).
- [x] **Declarative Registry**: Created `BRANCH_ROOTS` mapping to document and drive TUI hierarchy (Leaf -> Branch -> Trunk).
- [x] **Keyboard Efficiency**: Standardized `j/k/l` navigation across all sidebar levels and added `[`/`]` for instant sidebar/content focus switching.
- [x] **Smart Search Reset**: Returning to a branch root via `alt+s` now clears and targets the ListView for immediate browsing.

### Application Command Center
- [x] **Stacked Sidebar**: Implemented a space-efficient vertical menu for top-level categories and sub-category items.
- [x] **Cloud Scaling**: Added direct Fargate worker controls (0, 1, 5, 10 workers) to the Operations menu.
- [x] **Granular Sync**: Integrated individual queue (GM List, Details, Enrichment) and index synchronization.
- [x] **Maintenance Hub**: Added TUI support for index compaction (WAL -> Checkpoint) and local queue pushing.
- [x] **Session History**: Implemented a "Recent Runs" sidebar to track all background operations and their status.

### Observability & Performance
- [x] **Real-time Logs**: Implemented log capture and streaming for operations with a full history `LogViewerModal`.
- [x] **Cluster Monitoring**: Added SSH-based real-time health check (Status, Uptime, Voltage, Containers) for RPi nodes.
- [x] **Lazy Loading**: Optimized Application tab to open instantly, deferring heavy stats/SSH tasks until selected.
- [x] **Export Integration**: Automated report saving to campaign-specific `exports/report.json` for persistence.
- [x] **Hot-Reload Dev Flow**: Implemented `make dev` with `watchdog` for instant TUI restarts on code changes.

## Phase 6: Data Hygiene & Enrichment Stabilization (STABILIZED)
### Enrichment Pipeline Fixes
- [x] **Queue Misintegration**: Resolved path mismatches between worker leasing and supervisor tracking. Fixed `FilesystemEnrichmentQueue` to use consistent Ordinant-based S3 paths.
- [x] **S3 Auth Prioritization (Foundational Fix)**: Discovered that `DomainIndexManager` was bypasses centralized auth and hardcoding developer profiles. Refactored to use `get_boto3_session` which now automatically prioritizes `<campaign>-iot` profiles.
- [x] **Gold Standard Sharding**: Fully migrated enrichment queue to 2-character hex shards (`sha256(domain)[:2]`), resolving S3 listing bottlenecks.
- [x] **S3 Permission Audit**: Resolved `AccessDenied` errors on `cocli5x0` by isolating IoT certificates by campaign and fixing container-to-host path mapping.
- [x] **Legacy Purge**: Nuked all legacy `0x` hex ID files from WAL and recovery directories to prevent index pollution.
- [x] **Pipeline Visibility**: Implemented `cocli status --stats` to provide instant feedback on queue depth, in-flight tasks, and completion age.

### Remaining Work
- [ ] **Batch Enqueueing**: Hydrate the enrichment queue with the 29,493 prospects currently in the `roadmap` checkpoint.
- [ ] **Deduplication Tool**: Build a utility to find and merge duplicate companies (e.g., `a4-wealth-advisors` vs `a4wealth-com`).
- [ ] **Smart Merging**: Implement logic to prefer real names over slug-based names and ensure `place_id` and contact info are preserved during merge.

## Verification
- [x] `make test` passes (Lint + Unit tests green).
- [x] `prospects.checkpoint.usv` contains 29,493 unique records.
- [x] Enrichment queue backlog on S3 matches checkpoint domain count (~29k).
- [x] RPi heartbeats and WAL uploads are confirmed on S3 for all active nodes.
- [x] `cocli status --stats` confirms real-time processing rate (~1.5 items/min on Pi 5).
