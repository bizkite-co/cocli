# Task: UI/Service Layer Decoupling & Advanced TUI

## Objective
Formalize the interface between the CLI/TUI and the core business logic by centralizing operations in the Service Layer, while delivering a high-performance, high-density editing experience.

## Phase 1: Search & Navigation (Completed)
- [x] **Standardize Search**: `cocli/application/search_service.py` is now the sole provider for TUI and CLI fuzzy search.
- [x] **Performance Hardening**: DuckDB indexing optimized via native C++ parsing.
- [x] **VIM Navigation**: Implemented `hjkl` quadrant jumping and boundary-aware scrolling.

## Phase 2: Inline Editing & Filtering (Completed)
- [x] **Contact Filters**: Implemented "Actionable" lead filtering (Email OR Phone).
- [x] **Identity Editing**: Inline editing for Name, Domain, Email, Phone.
- [x] **Address Editing**: Expanded quadrant to support Street, City, State, and Zip edits.

## Phase 3: Advanced Editors & Consistency (Active)
- [ ] **Multi-line Notes**: Add a full-screen `TextArea` editor for the Notes quadrant.
- [ ] **Person Parity**: Update Person Detail view to match the 2x2 grid and support inline edits.
- [ ] **Campaign Consolidation**: Move `.envrc` and AWS Profile logic into `CampaignService.activate_campaign()`.

## Phase 4: Worker Service Extraction
- [ ] **Move Orchestration**: Create `cocli/application/worker_service.py` and move the async loops from `cocli/commands/worker.py`.

## Verification
- [x] `make test` passes (94/94).
- [x] Load times are < 1s for large datasets.
- [x] Inline edits persist correctly to YAML frontmatter.
