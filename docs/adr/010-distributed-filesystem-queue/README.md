# ADR 010: Distributed Filesystem Queue (DFQ) - Technical Index

This directory serves as the living documentation for the **Distributed Filesystem Queue (DFQ)**, a "zero-cost" task distribution system that leverages S3-synchronized storage and native S3 atomic operations.

## Architecture Evolution

The DFQ has evolved through three major iterations to handle increasing scale and reduce latency:

1.  **V1 (Basic Sync):** Relied on `aws s3 sync` for both discovery and claiming. Highly susceptible to race conditions.
2.  **V2 (Local Atomic Leases):** Introduced `os.O_EXCL` for local coordination, but still relied on sync for global visibility.
3.  **V3 (S3-Native Atomic Leases & Sharding):** Current implementation. Uses S3 `PutObject` with `If-None-Match: "*"` for global atomicity and randomized prefix sharding for efficient discovery.

## Documentation Components

- **[Local Lifecycle](local-lifecycle.md)**: Process-level coordination on a single host.
- **[S3/Global Lifecycle (ADR 011)](s3-lifecycle.md)**: Cluster-wide coordination using S3-native atomic operations.
- **[Randomized Sharding](sharding.md)**: Optimization strategy for task discovery in large queues.
- **[Point-to-Point Data Model](point-to-point.md)**: Strategy for reducing global synchronization overhead by fetching data on-demand.

## Key Performance Benefits

| Feature | Problem Solved | Impact |
| :--- | :--- | :--- |
| **Atomic S3 Leases** | Race conditions / Sync latency | Zero task double-processing. |
| **Prefix Sharding** | S3 `LIST` latency on large prefixes | Constant-time discovery. |
| **Point-to-Point** | High I/O and Bandwidth from global sync | ~90% reduction in supervisor sync traffic. |

## Related ADRs
- [ADR 010: Initial Filesystem Queue Design](../010-distributed-filesystem-queue.md)
- [ADR 011: S3-Native Conditional Leases Upgrade](../011-s3-native-conditional-leases.md)