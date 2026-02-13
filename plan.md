# Plan for `cocli` Development - Cloud Native Transition

This document outlines the roadmap for transitioning `cocli` from a purely local tool to a scalable, cloud-integrated platform using AWS Fargate and S3.

## Phase 1 to Phase 18: Completed (See Archives)
*Foundational cloud integration, distributed scraping, deterministic mission indexes, and campaign restoration.*

## Phase 19: UI/Service Layer Decoupling & API Formalization (Active)

**Goal:** Formalize the API between 'core' functionality and UIs (CLI, TUI, Web) and deliver a high-density VIM-like TUI.

1.  **Service Layer Infrastructure (Done):**
    *   [x] **ServiceContainer**: Implemented Dependency Injection for the TUI to decouple UI from business logic.
    *   [x] **SearchService**: Standardized DuckDB-based fuzzy search as the SSoT for both CLI (`fz`) and TUI.
    *   [x] **High-Performance Indexing**: Optimized DuckDB to use native C++ JSON parsing with explicit schemas (reduced load times from 15s to <0.1s).

2.  **High-Density VIM TUI (Done):**
    *   [x] **Cocli Theme**: Implemented a "Data-First" pure black theme with high-contrast grey/green highlights.
    *   [x] **Quadrant Navigation**: Implemented VIM-like `hjkl` navigation with boundary-aware jumping and sequential `[` / `]` cycling.
    *   [x] **Actionable Filters**: Added a contact-info filter (toggle `f`) to hide leads without reachable data (Email/Phone).
    *   [x] **Inline Editing**: Implemented seamless row-to-input switching for Name, Email, Phone, and Address fields.

3.  **Advanced Data Editing (Active):**
    *   [ ] **Multi-line Notes Editor**: Implement a full-screen or expanded modal editor for Note quadrants.
    *   [ ] **Person Detail Parity**: Refactor Person Detail to use the same 2x2 high-density quadrant layout.
    *   [ ] **Campaign Activation**: Move AWS profile and `.envrc` switching logic into `CampaignService.activate_campaign()`.

4.  **Worker Orchestration Decoupling:**
    *   [ ] Extract `run_worker`, `run_supervisor`, and `run_details_worker` from CLI commands into `WorkerService`.
    *   [ ] Standardize worker heartbeats and status reports as Pydantic models.
