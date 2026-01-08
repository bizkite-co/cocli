# Current Task: Infrastructure Standardization & Distributed Coordination

## Objective
Standardize resource naming across campaigns and implement distributed coordination for residential scraping nodes.

## Todo
- [ ] **Resource Naming Standardization:**
    - [ ] Refactor CDK to use `cocli-<resource>-<campaign>` naming convention.
    - [ ] Update infrastructure scripts to support the new naming pattern.
- [ ] **Distributed Coordination:**
    - [ ] Implement SQS-based distributed semaphore for IP-level throttling.
- [ ] **Campaign Configuration:**
    - [ ] Move worker hostnames to campaign `config.toml`.
- [ ] **Zero Error Maintenance:** 
    - [ ] Maintain 0 linting errors by running `make lint` before every commit.

## Done
- [x] **Deterministic Mission Indexing (Phase 10):**
    - [x] **Witness Index:** Workers now drop `.csv` proof-of-work files.
    - [x] **Idempotent Dispatcher:** `queue-mission` now uses set-difference (Targets - Witness) to prevent duplicates.
    - [x] **Global Sync:** Automated `smart-sync` of witness files before every mission dispatch.
- [x] **Cluster Powerhouse Architecture (Phase 11):**
    - [x] **Pi 5 Saturation:** Replaced fragile single-process supervisor with isolated scraper (8) and details (4) worker containers.
    - [x] **Central Path Authority:** Implemented `ValidatedPath` (ADR 009) to prevent relative path and symlink bugs.
    - [x] **Observability:** Updated KML generation and reports to use the new witness index.
- [x] **Infrastructure Hardening:**
    - [x] **Log Retention:** Enforced 3-day retention globally in CDK.
    - [x] **IAM Isolation:** Implemented tag-based Deny policy for campaign data isolation.
- [x] **Orchestration Module:**
    - [x] **CLI Commands:** Added `cocli infrastructure start-worker/stop-workers/deploy-creds`.
    - [x] **Consolidation:** Moved RPi setup and deployment logic into `cocli.core.infrastructure.rpi`.
- [x] **Cluster Expansion:**
    - [x] **Pi 5 Setup:** Successfully integrated Pi 5 with 4 concurrent details workers.
    - [x] **Pi 3 WiFi:** Created `scripts/setup_rpi_wifi.py` for automated WiFi configuration.
- [x] **Dashboard Modernization:**
    - [x] **Search UI:** Integrated PapaParse for client-side CSV searching.
    - [x] **Deployment Automation:** Updated `cocli web deploy` to run `npm run build`.