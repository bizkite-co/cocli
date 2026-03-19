# Discovery Audit Results

This directory is a **Frictionless Data Package**.

One `gm-list` `map-tile-id`/`search-phrase` combination produces multiple results.

That means that a file path with the map-tile ID and search phrase can contain multiple records in that file.

### Usage with DuckDB:
```sql
SELECT * FROM read_csv('completed/results/**/*.usv', delim='\x1f', header=false);
```

### Pipeline Transformation

These files are transformed into the prospects checkpoint via the [GmList to GoogleMapsProspect transformation](../../../../pipeline/gm-list/to-google-maps-prospect/).

Unlike traditional WAL files, **GmListResult files are kept after transformation** for tracing and debugging.

See [WAL Strategy](../../../wal-strategy.md) for the full compaction pipeline documentation.
