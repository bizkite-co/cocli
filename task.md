# Task: Screaming Architecture & Queue-Centric Operations

## Objective
Align the Python codebase with the Data Ordinance and implement a robust Queue Management system in the TUI to visualize and control the data pipeline (From-Model-to-Model).

## Phase 1-4: Completed ✅
- [x] Type-Safe Ordinant Protocol.
- [x] Hierarchical DataPaths (Dot-Notation).
- [x] Model Alignment (Company, Person, Tasks).
- [x] TUI Search Overhaul & Pathing Audit.

## Phase 5: Verification & Safety ✅
- [ ] **Ordinance Validation**: Add a startup check that verifies the first record of a sync matches the expected `docs/_schema/` path.
- [x] **Strict Test Isolation**: Implemented Atomic Root Authority in `paths.py` to prevent tests from mutating production data or configs.
- [x] **Automated Snapshot Refresh**: Integrated `playwright` into tests to automatically fetch fresh Google Maps HTML snapshots for parser verification.
- [x] **Tests**: Updated `tests/conftest.py` with `wait_for_widget` to eliminate race conditions in TUI tests.

## Phase 6: Queue Management & Transformation Visibility ✅
- [x] **Queue Metadata Registry**: Defined in `ReportingService` and TUI views.
- [x] **TUI Queue Viewer**:
    - [x] **Queue Selection Sidebar**: Added "Queues" to the Application tab.
    - [x] **Queue Detail Pane**: Displays data path, sharded counts, and live status.
    - [x] **Surgical Sync**: Implemented `sp` (sync pending) and `sc` (sync completed) shortcuts.
- [x] **The "To Call" Pipeline**:
    - [x] **Decoupled Queue (SSoT)**: Successfully moved "To-Call" leads from company tags into sharded USV pointers in `queues/to-call/pending/`.
    - [x] **Queue Builder (Promotion)**: Implemented `Compile To-Call List` workflow to tag top leads based on rating/reviews/contact-info.
- [x] **Transformation Insights**: Added "Schema" view showing `datapackage.json` field mappings and types.

## Phase 7: Operational Integrity & Cluster Sync (Active)
- [x] **Durable Operation Journals**: Implemented `runs/` folder with timestamped USVs for every major maintenance task.
- [x] **Live Checklist UI**: Real-time status markers (✔ success / ○ pending) in the Index/Operation views.
- [x] **Input Shield (Safety)**: Global focus protection to prevent shortcut hijacking during typing.
- [x] **Atomic Search Cache**: Implemented write-and-rename pattern in `build_cache` to eliminate truncated index reads.
- [ ] **Gossip-Based Queue Sync**: Enable compact datagram propagation (`Q:` records) for real-time task status sharing across the cluster.
- [ ] **Log Call Expansion**: Implement "Callback" scheduling logic that promotes companies to the To-Call queue on a specific date.
