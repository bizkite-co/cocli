# Task: Screaming Architecture & Immutable Transformers

## Objective
Isolate the data pipeline into role-based, least-privilege workers and implement immutable WASI-based transformers to ensure permanent field-level data integrity.

## Phase 5: Verification & Safety ✅
- [x] **Strict Test Isolation**: Implemented Atomic Root Authority in `paths.py`.
- [x] **Automated Snapshot Refresh**: Integrated `playwright` for parser verification.
- [x] **TUI Lead-Key INTERCEPTION**: Fixed leader-mode event bubbling to prevent focus-theft by child widgets.
- [ ] **Ordinance Validation**: Add startup check verifying first record matches `docs/_schema/` blueprint.

## Phase 6: Queue Management & Transformation Visibility ✅
- [x] **The "To Call" Pipeline**: Decoupled leads into sharded USV pointers in `queues/to-call/`.
- [x] **Ultra-Robust Parser**: Captured Griffith (4.7) and Granite (3.7) ratings via ARIA/Text nodes.
- [x] **Discovery "Witness" Mandate**:
    - [x] **Richer Discovery**: Expanded `gm-list` to 9 fields (domain, rating, gmb_url).
    - [x] **Deep-Sharding**: Aligned `gm-list` trace paths with the 3-level geo blueprint.
    - [x] **Anti-Destruction**: Updated compactor to NEVER unlink or delete session trace files.

## Phase 7: Role-Based Isolation (Active)
- [x] **Modular Processors**: Extracted `GmListProcessor` and `GoogleMapsDetailsProcessor` from the Fat Worker.
- [ ] **Docker Role-Splitting**: 
    - [ ] Create `cocli-scraper-gmaps`: Read-only queue access, write-only S3 RAW access.
    - [ ] Create `cocli-processor-gmb`: Read S3 RAW, write to sharded WAL (No browser).
- [ ] **Local RE-ENQUEUE Testing**:
    - [ ] **Manual Scrape**: Use `R` shortcut in TUI to verify `google_maps.usv` hydration.
    - [ ] **Discovery Trace**: Run local tile-phrase scrape and verify 9-column trace USV.

## Phase 8: Immutable WASI Transformers (Future)
- [ ] **Compaction Binary**: Compile USV-to-USV compactors to WebAssembly (WASI) to freeze transformation logic.
- [ ] **Model Linker**: Implement company-to-identity linkage in a isolated WASM sandbox to prevent "careless field discarding."
- [ ] **Gossip Sync**: Enable compact datagram propagation (`Q:` records) for real-time task status.
