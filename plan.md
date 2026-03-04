# Plan for `cocli` Development - Cloud Native Transition

This document outlines the roadmap for transitioning `cocli` from a purely local tool to a scalable, cloud-integrated platform using AWS Fargate and S3.

## Phase 1 to Phase 18: Completed (See Archives)
*Foundational cloud integration, distributed scraping, deterministic mission indexes, and campaign restoration.*

## Phase 19: UI/Service Layer Decoupling & API Formalization (Active)

**Goal:** Formalize the API between 'core' functionality and UIs (CLI, TUI, Web) and deliver a high-density VIM-like TUI.

1.  **Service Layer Infrastructure (Done):**
    *   [x] **ServiceContainer**: Implemented Dependency Injection for the TUI to decouple UI from business logic.
    *   [x] **SearchService**: Standardized DuckDB-based fuzzy search as the SSoT for both CLI (`fz`) and TUI.
    *   [x] **Atomic Data Rebuilding**: Implemented write-and-rename pattern to ensure search services never read partial or truncated indexes.
    *   [x] **Path Authority Stabilization**: Standardized on `.absolute()` pathing to resolve symlink mismatches and ensure portability.

2.  **High-Density VIM TUI (Done):**
    *   [x] **Cocli Theme**: Implemented a "Data-First" pure black theme with high-contrast grey/green highlights.
    *   [x] **Quadrant Navigation**: Implemented VIM-like `hjkl` navigation with boundary-aware jumping and sequential `[` / `]` cycling.
    *   [x] **Actionable Filters**: Added a contact-info filter (toggle `f`) to hide leads without reachable data (Email/Phone).
    *   [x] **Inline Editing**: Implemented seamless row-to-input switching for Name, Email, Phone, and Address fields.

3.  **Advanced Data Editing (Active):**
    *   [ ] **Multi-line Notes Editor**: Implement a full-screen or expanded modal editor for Note quadrants.
    *   [ ] **Person Detail Parity**: Refactor Person Detail to use the same 2x2 high-density quadrant layout.
    *   [ ] **Campaign Activation**: Move AWS profile and `.envrc` switching logic into `CampaignService.activate_campaign()`.

4.  **Worker Orchestration Decoupling (Done):**
    *   [x] **WorkerService Core**: Extracted `run_worker` and `run_orchestrated_workers` into a dedicated service layer.
    *   [x] **Real-Time Status**: Standardized `QueueDatagram` via Gossip Bridge for near-instant status reports.
    *   [x] **Container Networking**: Standardized on `--network host` for reliable cluster-wide discovery.

5.  **Automated Testing & Verification (Done):**
    *   [x] **Frictionless Test Harness**: Implemented automated snapshot refreshing for Google Maps scraper verification.
    *   [x] **Environment Shield**: Forced strict test re-rooting to prevent production data corruption.
    *   [x] **UI Synchronization**: Standardized on `wait_for_widget` to eliminate race conditions in TUI integration tests.
