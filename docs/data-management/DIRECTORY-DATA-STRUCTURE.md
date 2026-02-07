# Universal Data Namespace (Gold Standard)

This document defines the strictly enforced directory structure used across Local, S3, and Raspberry Pi environments.

## Core Principles

1.  **1:1 Mirroring**: Paths are identical in all environments. `/home/mstouffer/repos/data` on a Pi matches `s3://bucket/` matches `~/.local/share/cocli_data/`.
2.  **Sharding for Performance**: Large datasets (Prospects, Results) are sharded to prevent directory exhaustion and improve sync speed.
3.  **Frictionless USV**: Tabular data is stored as headerless `.usv` files with `UNIT_SEP` (\x1f). Schemas are defined in `datapackage.json`.
4.  **Identity Lineage**: Results are co-located with their geographic and keyword origins.

## Directory Layout

```text
data/
├── campaigns/
│   └── <campaign_name>/
│       ├── indexes/
│       │   ├── google_maps_prospects/  # Sharded by Place ID [shard_idx 5]
│       │   │   ├── A/
│       │   │   │   └── ChIJA...usv     # Headerless: place_id | slug | ...
│       │   │   └── ...
│       │   └── emails/                 # Sharded by Domain [shard_idx 0]
│       │
│       ├── queues/
│       │   ├── gm-list/
│       │   │   ├── pending/            # Geographic Sharding [lat 1-dec]
│       │   │   │   └── 3/34.1/-84.5/   # shard=lat[0]
│       │   │   │       ├── task.json
│       │   │   │       └── lease.json
│       │   │   └── completed/          # Witness Index
│       │   │       └── 3/34.1/-84.5/   # shard=lat[0]
│       │   │           └── <phrase>.usv # Result summary
│       │   │
│       │   └── gm-details/
│       │       ├── pending/            # Same sharding as gm-list
│       │       └── completed/          # Witness Index [Receipts]
│       │           └── <place_id>.json
│       │
│       └── datapackage.json            # Frictionless Schemas for all USVs
```

## Data Formats

### USV (Unit Separated Values)
- **Field Separator**: `UNIT_SEP` (`\x1f`)
- **Record Separator**: `\n` (Newline)
- **Headers**: OMITTED.
- **Identifiers**: The first two columns MUST be `place_id` and `company_slug`.

### JSON
- **Tasks**: `task.json` contains the model-validated instructions for a worker.
- **Markers**: `completed/<id>.json` contains the verified receipt of work.

## Synchronization (The "Smart-Sync" Standard)

- **Local -> S3**: Use `cocli smart-sync all`.
- **S3 -> Local**: `cocli smart-sync` pulls only updates based on `.smart_sync_state.json`.
- **Atomic Deletions**: Use `aws s3 sync --delete` ONLY on specific leaf folders (e.g., `completed/`) after local auditing.

---
*See `docs/.schema/traceability.md` for how identities move through this structure.*
