# Task: Screaming Architecture & Queue-Centric Operations

## Objective
Align the Python codebase with the Data Ordinance and implement a robust Queue Management system in the TUI to visualize and control the data pipeline (From-Model-to-Model).

## Phase 1-4: Completed ✅
- [x] Type-Safe Ordinant Protocol.
- [x] Hierarchical DataPaths (Dot-Notation).
- [x] Model Alignment (Company, Person, Tasks).
- [x] TUI Search Overhaul & Pathing Audit.

## Phase 5: Verification & Safety
- [ ] **Ordinance Validation**: Add a startup check that verifies the first record of a sync matches the expected `docs/_schema/` path.
- [x] **Tests**: Update `tests/test_paths.py` to verify the new hierarchical pathing.

## Phase 6: Queue Management & Transformation Visibility (NEW)
- [ ] **Queue Metadata Registry**: Define formal metadata for each queue (gm-list, gm-details, enrichment, to-call) including labels, model mapping, and sharding strategies.
- [ ] **TUI Queue Viewer**:
    - [ ] **Queue Selection Sidebar**: Add "Queues" to the Application tab.
    - [ ] **Queue Detail Pane**: Display data path, from/to model properties, and sharded counts (pending/completed).
    - [ ] **Surgical Sync**: Implement buttons to sync *only* the specific queue branch (Pending vs. Completed).
- [ ] **The "To Call" Pipeline**:
    - [ ] **Queue Definition**: Create `ToCallTask` model and directory structure in `data/campaigns/{slug}/queues/to-call/`.
    - [ ] **Queue Builder (Promotion)**: Implement a command/service to find enriched companies missing the `contacted` tag and enqueue them for calling.
- [ ] **Transformation Insights**: Add a "Model Schema" view that shows exactly how fields are mapped during the transformation (e.g., `GmItemTask.place_id` -> `Company.place_id`).
