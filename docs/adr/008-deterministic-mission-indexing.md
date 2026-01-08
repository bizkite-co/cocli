# ADR 008: Deterministic Mission Indexing via Distributed Witness Files

## Status
Accepted (Implemented in Phase 10 & 11)

## Context
...
(Content remains same until Decision)
...

## Decision
...
(Content remains same until Implications)
...

## Implementation Notes (Post-Phase 11)

### 1. Process Isolation (The Powerhouse)
During the implementation on high-performance nodes (Raspberry Pi 5), we discovered that a single-process `supervisor` using `asyncio` to manage multiple Playwright instances created a resource contention bottleneck. 
- **Correction:** We shifted to **Isolated Worker Containers**. Each worker (Scrape or Details) runs in its own Docker container with a dedicated memory pool.
- **Benefit:** This prevents "Single Point of Failure" deadlocks and allows the Linux kernel to handle CPU scheduling more efficiently across cores.

### 2. Witness Authority
The `ScrapeIndex` was refactored to treat the `.csv` witness files as the "Ground Truth." Legacy JSON files are still supported for backward compatibility but are effectively deprecated for new scrapes.

### 3. Path Robustness
The implementation of this ADR necessitated the creation of a **Central Path Authority** (ADR 009) to ensure that distributed nodes always resolve witness paths identically, regardless of relative working directories or symlinks.


## References & Deep Dive Topics for Study
- **Content-Addressable Storage (CAS):** See IPFS, Git, and Git-Annex.
- **Eventual Consistency in Distributed Systems:** How we handle two workers finishing the same tile at once (Conflict-Free Replicated Data Types - CRDTs).
- **Local-First Software:** The philosophy that the user (or worker) owns their data and syncs only when necessary (see Ink & Switch research).
- **Filesystem-as-a-Database:** The pattern used by tools like Maildir or the Git object store.
