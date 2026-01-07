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