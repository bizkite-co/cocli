# Task: Screaming Architecture & Immutable Transformers

## Objective
Isolate the data pipeline into role-based, least-privilege workers and implement immutable WASI-based transformers to ensure permanent field-level data integrity.

## Phase 9: Hardened Security & WASI
- [ ] **Least-Privilege AWS Roles**:
    - [ ] **Scraper Policy**: Allow `s3:PutObject` to `raw/`, `s3:GetObject` from `queues/`.
    - [ ] **Processor Policy**: Allow `s3:GetObject` from `raw/`, `s3:PutObject` to `wal/`.
- [ ] **WASI Compaction**:
    - [ ] Compile USV compactors to WASM to freeze transformation logic.
    - [ ] Designated PI runner for compaction-only role.
- [ ] **Gossip Data Bridge**: 
    - [ ] Use gossip bridge to signal compaction completion.
    - [ ] Stream compacted index data directly between nodes (P2P).

## Phase 10: Structural Audit & Screaming Architecture
- [x] **CLI Structure Dump**:
    - [x] Implement command hierarchy dumper for Typer in `cocli audit cli`.
    - [x] Documented in [docs/cli/README.md](docs/cli/README.md).
- [x] **Project Integrity**:
    - [x] Decouple CLI commands and TUI from `make` dependencies (Cluster stop, Infra deploy).
    - [x] Implement and install Git `pre-commit` hook requiring `make test`.
    - [x] Implement code signature hashing for incremental `make build`.
- [x] **Filesystem Audit**:
    - [x] Implement directory structure reporter for 'Screaming' compliance in `cocli audit fs`.
    - [x] Documented in [docs/fs/README.md](docs/fs/README.md).
- [x] **Rollout Audit**:
    - [x] Fix S3 path mismatch bug in `WildernessManager`.
    - [x] Implement `cocli audit rollout` for automated batch diagnostics.
    - [x] Integrated into `make rollout-audit`.
