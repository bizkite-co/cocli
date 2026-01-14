# ADR 011: S3-Native Conditional Leases for DFQ

## Status
Implemented (2026-01-13)

## Context
Our initial Distributed Filesystem Queue (DFQ) design relied on local atomic file operations (`os.O_EXCL`) and periodic S3 synchronization via the `supervisor`. 

As our data scales (10,000+ companies, 4,000+ queue items), this model is hitting bottlenecks:
1. **Sync Latency**: A 60-second sync window allows for race conditions where multiple nodes claim the same task.
2. **I/O Pressure**: RPI nodes spend significant CPU/IO listing and comparing thousands of local and remote files.
3. **S3 Costs**: Frequent `LIST` operations on large prefixes increase API costs and latency.

## Decision
Transition from filesystem-synced leases to **S3-Native Conditional Leases** using S3's atomic `PutObject` with `If-None-Match: "*"` support.

### Technical Implementation
The details of the S3-Native lifecycle, including sharding and discovery, are now maintained in the unified DFQ documentation:

**[docs/adr/010-distributed-filesystem-queue/s3-lifecycle.md](010-distributed-filesystem-queue/s3-lifecycle.md)**

### Architecture Components
1. **Atomic Claim**: S3 `PutObject` with `IfNoneMatch: '*'`.
2. **[Discovery Optimization](010-distributed-filesystem-queue/sharding.md)**: Randomized prefix sharding.
3. **[Data Efficiency](010-distributed-filesystem-queue/point-to-point.md)**: Point-to-Point fetching.

## Consequences
- **Pros**:
  - Global atomicity (zero race conditions).
  - Reduced local I/O on RPIs.
  - Faster task distribution (no waiting for sync cycles).
  - Massive reduction in bandwidth/IO via Point-to-Point data.
- **Cons**:
  - Requires active internet connection (DFQ V2 was partially offline-capable).
  - Increased S3 `PUT` operations (though still very cheap).
  - Discovery is probabilistic when the queue is nearly empty.
