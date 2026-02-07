# Google Maps List Queue (`gm-list`)

This queue consumes the geographic targets produced by `discovery-gen`.

## Process
- **Worker**: Navigates to a specific `lat/lon` tile.
- **Search**: Executes a specific `<phrase>` search.
- **Extraction**: Collects all visible `Place_ID`s.

## Output
- **Witness Record**: `queues/gm-list/completed/{shard}/{lat}_{lon}/{phrase}.usv`
- **Identity Feed**: New `Place_ID`s are automatically enqueued into `gm-details/pending/`.