# Task: Implement Managed Store Protocols

## Objective
Define formal `typing.Protocol` interfaces for all sharded data stores (Indexes, Queues, Witness collections). This ensures that any service interacting with the filesystem or S3 uses a standardized API instead of calculating paths manually.

## Background
We currently have ad-hoc path logic in `WildernessManager`, `FilesystemQueue`, and various scripts. This led to the `scraped_areas` vs `scraped-tiles` mismatch.

## Requirements
- Define `ManagedStore` protocol in `cocli/core/store/base.py`.
- Interface should include:
    - `root`: Base Path authority.
    - `resolve(identity)`: Deterministic path for a specific object.
    - `sync()`: Parity enforcement between Local and S3.
- Implement for:
    - `ScrapedTilesStore`
    - `ProspectsStore`
    - `EmailStore`

## Context
- **See also**: [implement-service-protocols.md](docs/issues/draft/implement-service-protocols.md)
- **Path Authority**: `cocli/core/paths.py`
