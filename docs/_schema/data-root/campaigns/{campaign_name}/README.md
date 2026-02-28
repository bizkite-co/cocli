# Campaign Schema: {campaign_name}

This directory is the root of all campaign-specific operations. It follows a strict "Screaming Architecture" where the structure reveals the intent.

## Top-Level Sibling Directories

### `indexes/`
The "Gold Standard" data. Contains the Write-Ahead Log (WAL) and compacted Checkpoints. This is the source of truth for the TUI and exports.

### `queues/`
Lightweight task markers and completion receipts. Designed for sub-second synchronization to keep the cluster and local machines in sync.

### `raw/`
The "Witness Landing Zone." Heavyweight raw data captures (HTML/JSON) preserved for auditability. Isolated here to prevent queue sync bloat.

### `resources/`
Mission-level assets, including KML coverage maps, target location CSVs, and testimonial data.

## Data Ordinance
Every file must follow deterministic sharding (Geo or ID-based) to ensure 1:1 mirroring between local and S3 without collisions.
