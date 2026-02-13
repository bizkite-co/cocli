# Cocli Filesystem & S3 Schema Specification

This directory uses the filesystem itself to document the expected structure of data across different environments (Local, S3, RPi). 

## The Unified Coordinate Policy (UCP)
`cocli` adheres to a strict 1:1 mapping between **Data Identity**, **Storage Path**, and **UI Navigation**. Every actionable element in the system is addressed by a "Unified Coordinate" (or Ordinant).

### 1. The Hierarchy of Ordinants
A coordinate is composed of segments that define its location across all layers:
`{CAMPAIGN} / {COLLECTION} / {ENTITY} / {QUADRANT} / {FIELD}`

*   **Example Path**: `roadmap / companies / auctus-advisors / info / phone_number`
*   **TUI Mapping**: `CompanyDetail(slug="auctus-advisors")` -> `InfoTable` -> `Row("Phone")`
*   **Storage Mapping**: `~/.local/share/cocli_data/companies/auctus-advisors/_index.md` -> `yaml["phone_number"]`
*   **S3 Mapping**: `s3://cocli-data-roadmap/companies/auctus-advisors/_index.md`

### 2. Policy Requirements
- **Path-as-Identity**: No data should exist without a deterministic path. We do not use auto-incrementing IDs; we use slugs and coordinates.
- **TUI-to-Path Transparency**: Every widget in the TUI should be able to resolve its "Origin Path." When you press `Enter` to edit, the widget knows exactly which file and key it is modifying because they share the same coordinate.
- **Targeted Propagation**: Sync operations (via S3, FreeNet, or IPFS) should prioritize the smallest possible leaf node defined by the coordinate to minimize collision and bandwidth.

## Structure
- `local/`: Standard structure for local development and campaign data.
- `s3-bucket/`: Standard namespace for the campaign S3 data bucket.
- `rpi-worker/`: Structure inside the Raspberry Pi Docker containers.

## Validation & Testing
1. **Ordinant Checks**: Test suites (including BDD features) should use coordinates to set up and verify state (e.g., "Given the coordinate `X` has value `Y`").
2. **Environment Audit**: A script can walk an environment and flag any paths that do not exist in this schema tree.

## Legend
- `README.md`: Describes the purpose of a directory or node.
- `*.schema.json`: JSON Schema defining the file format.
- `example.*`: A valid example file.
