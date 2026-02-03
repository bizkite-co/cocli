# Task: Roadmap Campaign Identity Recovery & Shielding

## Objective
Recover 18,451 hollow `roadmap` prospect records and implement an "Identification Shield" to prevent future metadata loss using data-driven regression testing and semantic selectors.

## Phase 1: Infrastructure & Integrity (COMPLETED)
- [x] **Centralized Sharding**: Implemented 16-way index-5 sharding (`identifier[5]`) to avoid "ChIJ-" prefix collisions.
- [x] **Model Standardization**: Restored `AwareDatetime` and `PhoneNumber` types in `GoogleMapsProspect`.
- [x] **Queue Re-sharding**: Verified S3 DFQ paths match the new index-5 logic.
- [x] **Cluster Readiness**: Provisioned `cocli5x0.pi`, `coclipi.pi`, and `cocli5x1.pi`.

## Phase 2: Identification Shield & Regression Testing (CURRENT)
- [x] **Golden Set Definition**: Created `tests/data/maps.google.com/golden_set.usv` with diverse, stable ground-truth data.
- [x] **Snapshot Pipeline**: Implemented `scripts/capture_maps_snapshot.py` to simulate Search -> List -> Detail workflow and generate fresh HTML for testing.
- [x] **Semantic Selectors**: Refactored `parse_gmb_page` to prioritize ARIA labels and semantic roles over brittle CSS classes (e.g., `hfpxzc`, `qBF1Pd`).
- [ ] **Strict Identity Model**: Update `GoogleMapsProspect` to make `name` and `company_slug` **REQUIRED**.
    - *Goal*: Pydantic `ValidationError` must trigger on any record missing identity, preventing the save of hollow USV files.
- [ ] **Identity Preservation**: Update `GmItemTask` to carry `name` and `company_slug` from the `gm-list` phase to ensure identity is preserved even if the detail parser fails.
- [ ] **Shield Verification**: Ensure the `gm-details` worker handles model validation errors by `nack`-ing the task (triggering a retry) instead of failing silently.

## Phase 3: Recovery Execution
- [ ] **Enqueuing**: Populate the `gm-details` queue with the 18,451 hollow Place IDs from `hollow_place_ids.usv`.
- [ ] **Cluster Processing**: Monitor RPI nodes as they re-scrape metadata and populate the sharded index.
- [ ] **Verification**: Run a post-recovery audit to ensure the number of hollow records has dropped to near-zero.

## Technical Standards (Updated)
- **Scraping Integrity**: Mandatory use of `USER_AGENT` and `ANTI_BOT_HEADERS` from `cocli.utils.headers`.
- **Selector Policy**: Avoid all obfuscated/auto-generated CSS classes. Use ARIA labels, roles, and data-attributes (e.g., `data-item-id="authority"`).
- **Test-Driven**: All parser changes must be verified against the `Golden Set` snapshots (`pytest tests/unit/test_google_maps_parser.py`).
- **Field Separator**: `\x1f` (Unit Separator)
- **Identity Anchor**: `place_id` (Primary) + `company_slug` (Required for Prospect status).
