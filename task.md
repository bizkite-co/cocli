# Task: Screaming Architecture & Immutable Transformers

## Objective
Isolate the data pipeline into role-based, least-privilege workers and implement immutable WASI-based transformers to ensure permanent field-level data integrity.

## Phase 6: Queue Management & Transformation Visibility ✅
- [x] **The "To Call" Pipeline**: Decoupled leads into sharded USV pointers.
- [x] **Ultra-Robust Parser**: Captured Griffith (4.7) and Granite (3.7) via ARIA/Text nodes.
- [x] **Discovery "Witness" Mandate**:
    - [x] **Richer Discovery**: Expanded `gm-list` to 9 fields (domain, rating, gmb_url).
    - [x] **Deep-Sharding**: Aligned `gm-list` trace paths with 3-level geo blueprint.
    - [x] **Anti-Destruction**: Compactor strictly preserves session trace files.

## Phase 7: Role-Based Isolation & Cluster Deployment ✅
- [x] **Modular Processors**: Extracted `GmListProcessor` and `GoogleMapsDetailsProcessor`.
- [x] **Role-Aware Workers**: Added `--role scraper` and `--role processor` modes.
- [x] **Safe RPI Deployment**: Standardized `make hotfix-cluster-safe` (Hub-Registry-Propagation).
- [x] **High-Fidelity Recovery Scraper**:
    - [x] **State Machine Refactor**: Formalized `GoogleMapsDetailsScraper` with auditable phases (Warmup, Navigate, Heal, Capture).
    - [x] **Pre-Flight Warmup**: Bypassed "Limited View" cloaking via `google.com/maps` session establishment.
    - [x] **Session-Heal**: Implemented aggressive semantic hydration clicks (jsaction-based).
    - [x] **Deduplicating Compactor**: DuckDB-powered clean index rewrite (Reduced 256MB -> 10MB).
- [x] **Bulk Recovery (10k Scrape)**:
    - [x] Created `scripts/enqueue_bulk_recovery.py` with positional DuckDB query.
    - [x] Enqueued 10,000 targets into `gm-details` queue on S3.
    - [x] Swapped RPI fleet to `--role scraper` mode via `swap_cluster_role.sh`.

## Phase 8: Hardened Security & WASI (Future)
- [ ] **Least-Privilege AWS Roles**:
    - [ ] **Scraper Policy**: Allow `s3:PutObject` to `raw/`, `s3:GetObject` from `queues/`.
    - [ ] **Processor Policy**: Allow `s3:GetObject` from `raw/`, `s3:PutObject` to `wal/`.
- [ ] **WASI Compaction**:
    - [ ] Compile USV compactors to WASM to freeze transformation logic.
    - [ ] Designated PI runner for compaction-only role.
- [ ] **Gossip Data Bridge**: 
    - [ ] Use gossip bridge to signal compaction completion.
    - [ ] Stream compacted index data directly between nodes (P2P).
