# Raw Data Landing Zone (raw/)

This directory contains immutable "Witness" captures of raw data before transformation. It is separated from `queues/` and `indexes/` to allow for selective synchronization (bulky HTML vs. lightweight markers).

## Structure

### Google Maps Details (`raw/gm-details/`)
Stores the full HTML and metadata for individual Place ID scrapes.
- **Path**: `{shard}/{place_id}/`
- **Files**:
  - `metadata.json`: Capture timing, worker ID, and URL.
  - `witness.html`: The full hydrated DOM at time of capture.

### Google Maps List (`raw/gm-list/`)
*Planned/Active*: Stores the HTML fragments for individual search result items.
- **Path**: `{lat_shard}/{lat_tile}/{lon_tile}/{place_id}.html`
- **Note**: These are mirrored from the `queues/gm-list/completed/results/` directory to prevent bloated queue syncs.

## Witness Mandate
1. **Immutability**: Once a witness is written, it must NEVER be modified.
2. **Traceability**: Every Gold record in the WAL must point back to a witness.
3. **Preservation**: Compactors may move witnesses to `completed/` but must NEVER delete them.
