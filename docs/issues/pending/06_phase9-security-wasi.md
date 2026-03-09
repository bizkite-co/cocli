# Task: Hardened Security & WASI (Phase 9)

## Objective
Isolate the data pipeline into role-based, least-privilege workers and implement immutable WASI-based transformers.

## Requirements
- **Least-Privilege AWS Roles**:
    - **Scraper Policy**: Allow `s3:PutObject` to `raw/`, `s3:GetObject` from `queues/`.
    - **Processor Policy**: Allow `s3:GetObject` from `raw/`, `s3:PutObject` to `wal/`.
- **WASI Compaction**:
    - Compile USV compactors to WASM to freeze transformation logic.
    - Designated PI runner for compaction-only role.
- **Gossip Data Bridge**: 
    - Use gossip bridge to signal compaction completion.
    - Stream compacted index data directly between nodes (P2P).
