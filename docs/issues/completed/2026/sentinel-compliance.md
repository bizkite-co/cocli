# Task: Implement Sentinel Compliance for OMAP Stores

## Objective
Implement a "Sentinel Constraint" where every directory managed by cocli must verify its identity via a `datapackage.json` file before any write operation is permitted.

## Background
The "scraped_areas" bug was noticeable because the folder names were similar but different. A sentinel file makes the intended purpose of a directory unambiguous to both the developer and the machine.

## Requirements
- Add `verify_sentinel()` to the `ManagedStore` protocol.
- Check `datapackage.json` -> `name` matches the expected `StoreIdentity`.
- Fail loudly if a service attempts to write to an un-sentineled or mismatched directory.
