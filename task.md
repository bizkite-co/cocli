# Task: Roadmap Campaign Identity Recovery & Shielding

## Objective
Recover 18,451 hollow `roadmap` prospect records and implement an "Identification Shield" to prevent future metadata loss.

## Phase 1: Infrastructure & Integrity (COMPLETED)
- [x] **Centralized Sharding**: Implemented 16-way index-5 sharding (`identifier[5]`) to avoid "ChIJ-" prefix collisions.
- [x] **Model Standardization**: Restored `AwareDatetime` and `PhoneNumber` types in `GoogleMapsProspect`.
- [x] **Queue Re-sharding**: Verified S3 DFQ paths match the new index-5 logic.
- [x] **Cluster Readiness**: Provisioned `cocli5x0.pi`, `coclipi.pi`, and `cocli5x1.pi`.

## Phase 2: Identification Shield (CURRENT)
- [ ] **Strict Identity Model**: Update `GoogleMapsProspect` to make `name` and `company_slug` **REQUIRED**.
    - *Goal*: Pydantic `ValidationError` must trigger on any record missing identity, preventing the save of hollow USV files.
- [ ] **Worker Resilience**: Ensure the `gm-details` worker handles model validation errors by `nack`-ing the task (triggering a retry) instead of failing silently.

## Phase 3: Recovery Execution
- [ ] **Enqueuing**: Populate the `gm-details` queue with the 18,451 hollow Place IDs from `hollow_place_ids.usv`.
- [ ] **Cluster Processing**: Monitor RPI nodes as they re-scrape metadata and populate the sharded index.
- [ ] **Verification**: Run a post-recovery audit to ensure the number of hollow records has dropped to near-zero.

## Phase 4: Cleanup (Sidelined/Deferred)
- [ ] **DLQ Implementation**: Create a formal `dead_letter/` directory for persistent scrape failures.
- [ ] **Lightweight Index**: Build a `GoogleMapsIndex` (`place_id`, `company_slug`) from the compiled sharded USVs.

## Technical Standards
- **Field Separator**: `\x1f` (Unit Separator)
- **Record Separator**: `\n` (Standard Newline)
- **Identity Anchor**: `place_id` (Primary) + `company_slug` (Required for Prospect status).