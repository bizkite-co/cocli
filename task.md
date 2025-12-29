# Current Task: Reliability & Process Hardening

## Objective
Ensure the distributed scraping and enrichment pipeline is 100% reliable through strict process guardrails, robust container bootstrapping, and automated infrastructure synchronization.

## Context
*   **Status:** Distributed workers (RPi & Fargate) are active.
*   **Architecture:** Shifted to a single-tenant, configuration-driven model where each campaign has isolated resources.
*   **Dashboard:** `cocli.turboheat.net` is live with 11ty, providing dynamic reports and CSV downloads.
*   **Pipeline:** 1,000+ GM List items queued; Details workers processing and feeding Enrichment queue.

## Todo
- [ ] **Worker Monitoring:**
    - [ ] **Centralized Logging:** Implement logic to aggregate RPi container logs into S3 or CloudWatch for unified debugging.
    - [ ] **Health Checks:** Add a watchdog to restart workers if they fail to poll SQS for > 15 minutes.
- [ ] **Scale-Out:**
    - [ ] **Worker Management:** Streamline the multi-Pi deployment process (maybe a `make deploy-all-rpis` command).
- [ ] **Zero Error Maintenance:** 
    - [ ] Maintain 0 linting errors by running `make lint` before every commit.

## Done
- [x] **Web Dashboard (Phase 5):**
    - [x] Initialized `11ty` in `cocli/web/` for minimalist rendering.
    - [x] Implemented shared navbar and layout.
    - [x] Created home page at `cocli.turboheat.net`.
    - [x] Updated `cocli report` to output `report.json` and upload to S3.
    - [x] Updated `make export-emails` to automatically sync CSV to S3.
- [x] **Zero-Error Linting:** Resolved 120+ `mypy` and `ruff` errors to clear the noise and prevent hidden regressions.
- [x] **Build Guardrails:** 
    - [x] Integrated `ruff check` into `Dockerfile`.
    - [x] Added import verification to `Dockerfile`.
    - [x] Enforced `ruff` check in `make deploy-rpi`.
- [x] **Config-Driven Architecture:**
    - [x] Isolated SQS/S3 resources per campaign.
    - [x] Created `scripts/update_campaign_infra_config.py` for automated AWS -> Local sync.
    - [x] Implemented S3 config bootstrapping for remote RPi workers.
- [x] **Sync Optimization:** 
    - [x] Implemented `cocli smart-sync` command with incremental sync logic and progress bars.