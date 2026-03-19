# GmListResult to GoogleMapsProspect

Compacts Google Maps list scraping results into the main prospects checkpoint index.

## Overview

```
queues/gm-list/completed/results/
    └── {shard}/{lat}/{lon}/{phrase}.usv
            │
            ▼
    GoogleMapsListItem (source)
            │
            ▼
    [Compaction Transformer]
            │
            ▼
    GoogleMapsProspect (destination)
            │
            ▼
    indexes/google_maps_prospects/prospects.checkpoint.usv
```

## Source Model

**Type**: `GoogleMapsListItem`
**Location**: `queues/gm-list/completed/results/`
**Path**: `cocli.models.campaigns.indexes.google_maps_list_item.GoogleMapsListItem`

### Schema

| Field | Type | Description |
|-------|------|-------------|
| `place_id` | string | Google Place ID (primary key) |
| `company_slug` | string | Generated slug for the business |
| `name` | string | Business name |
| `phone` | string | Phone number |
| `domain` | string | Extracted domain |
| `reviews_count` | integer | Number of reviews |
| `average_rating` | float | Average rating |
| `street_address` | string | Street address |
| `gmb_url` | string | Google Maps URL |

### Non-Serialized Metadata (Excluded from USV)

| Field | Description |
|-------|-------------|
| `discovery_phrase` | Search phrase that found this result |
| `discovery_tile_id` | Tile ID of discovery location |
| `html` | Raw HTML of list item |

## Destination Model

**Type**: `GoogleMapsProspect`
**Location**: `indexes/google_maps_prospects/`
**Path**: `cocli.models.campaigns.indexes.google_maps_prospect.GoogleMapsProspect`

### Schema (Subset)

| Field | Source Field | Notes |
|-------|-------------|-------|
| `place_id` | `place_id` | Direct map |
| `company_slug` | `company_slug` | Direct map |
| `name` | `name` | Direct map |
| `phone` | `phone` | Direct map |
| `reviews_count` | `reviews_count` | Direct map |
| `average_rating` | `average_rating` | Direct map |
| `street_address` | `street_address` | Direct map |
| `gmb_url` | `gmb_url` | Direct map |

### Generated Fields

| Field | Source | Notes |
|-------|--------|-------|
| `created_at` | file mtime | From GmListResult file |
| `updated_at` | now() | Set to compaction time |
| `keyword` | `discovery_phrase` | Rename |
| `processed_by` | "pi-sync" | Set by transformer |

## Field Transformations

### Required Mappings

```python
def transform(source: GoogleMapsListItem) -> dict:
    return {
        "place_id": source.place_id,
        "company_slug": source.company_slug,
        "name": source.name,
        "phone": source.phone,
        "domain": source.domain,
        "reviews_count": source.reviews_count,
        "average_rating": source.average_rating,
        "street_address": source.street_address,
        "gmb_url": source.gmb_url,
        # Generated
        "keyword": source.discovery_phrase,  # Rename
        "processed_by": "pi-sync",
        "created_at": file_mtime,  # From source file
        "updated_at": now(),  # Compaction time
    }
```

### Discarded Fields

- `discovery_tile_id` - Index-only metadata
- `html` - Debug only, not persisted

## Deduplication Strategy

### Primary Key
`place_id` - Google Place ID is the unique identifier

### Conflict Resolution
**Last-Write-Wins (LWW)** based on:
1. `updated_at` timestamp (if available)
2. File modification time
3. Alphabetical order (fallback)

### Deduplication Against

1. Existing `prospects.checkpoint.usv`
2. Other GmListResult files being processed

## Implementation Notes

### KEEP Source Files
Unlike traditional WAL compaction, GmListResult files are **kept** after transformation:
- Valuable for tracing/debugging data pipeline
- Evidence of scraping origin
- Useful for leak detection

### DuckDB Transformation

```python
def compact_gm_list_results(
    results_dir: Path,
    checkpoint_path: Path,
    campaign_name: str
) -> int:
    """
    Compacts GmListResult USVs into prospects checkpoint.
    
    Returns: Number of records merged
    """
    import duckdb
    
    con = duckdb.connect(database=':memory:')
    
    # Load existing checkpoint
    con.execute(f"""
        CREATE TABLE checkpoint AS 
        SELECT * FROM read_csv_auto('{checkpoint_path}')
    """)
    
    # Load GmListResult files
    results_pattern = f"{results_dir}/**/*.usv"
    con.execute(f"""
        CREATE TABLE gm_results AS
        SELECT * FROM read_csv('{results_pattern}', ...)
    """)
    
    # Merge with deduplication
    con.execute("""
        CREATE TABLE merged AS
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY place_id 
                ORDER BY updated_at DESC NULLS LAST) as rn
            FROM (
                SELECT * FROM checkpoint
                UNION ALL
                SELECT * FROM gm_results
            )
        ) WHERE rn = 1
    """)
    
    # Write output
    con.execute(f"""
        COPY merged TO '{checkpoint_path}' (DELIMITER '\x1f')
    """)
    
    return con.execute("SELECT COUNT(*) FROM merged").fetchone()[0]
```

## Related Documents

- [WAL Strategy](../../wal-strategy.md) - General WAL documentation
- [Pipeline Index](../README.md) - All transformations
- [GmListResult Schema](./schema/) - Source schema reference
