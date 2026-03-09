# Filesystem Structure

This directory contains the documentation for the cocli Filesystem hierarchy (OMAP).

## Implementation Status

- **Auditor:** `cocli audit fs --output docs/fs/actual_tree.txt`
- **Trigger:** `make fs-tree`

## Principles

The filesystem follows the **OMAP (Ordinant Mapping)** standard, also known as "Screaming Architecture".
Deterministic paths are used for campaigns, indexes, and queues to support sharded, distributed processing.

## Audit Legend

- **[VALID]:** Path exists and matches OMAP expectations.
- **[MISSING]:** Path is required by OMAP but does not exist.
- **[ORPHAN]:** Path exists but is not recognized or allowed by OMAP.
- **[ERROR]:** An error occurred while auditing this path.
