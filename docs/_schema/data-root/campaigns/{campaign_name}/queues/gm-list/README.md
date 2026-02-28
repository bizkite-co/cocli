# Google Maps List Queue (`queues/gm-list/`)

Handles the discovery of prospects via geographic tile-based search phrases.

## Structure

### Pending (`pending/`)
- **Path**: `{lat_shard}/{lat}/{lon}/{phrase}.csv`
- **Format**: Lightweight CSV markers for work.

### Completed (`completed/`)
Stores completion receipts and search results.

#### Results (`completed/results/`)
- **Path**: `{lat_shard}/{lat_tile}/{lon_tile}/`
- **Files**:
  - `{phrase}.usv`: High-fidelity USV results (9 columns).
  - `{phrase}.json`: Completion receipt (timing, count, worker).
  - *Deprecated*: `{place_id}.html` (Moved to sibling `raw/` directory for sync efficiency).

## Sync Policy
`cocli smart-sync queues` downloads these directories frequently to update the local TUI and task lists. By keeping HTML out of this branch, sync times remain sub-second.
