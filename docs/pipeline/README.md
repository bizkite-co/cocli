# Data Pipeline Transformations

This directory contains specifications for all [from-model-to-model](../adr/from-model-to-model.md) transformations in the data pipeline.

## Transformation Index

| Source | Destination | Status | Description |
|--------|-------------|--------|-------------|
| [GmListResult](./gm-list/) | GoogleMapsProspect | Planned | Compacts PI scraped results into main index |

## About WAL Pattern

All transformations follow the [WAL Strategy](../wal-strategy.md) pattern:
- Workers append to WAL files
- Compaction merges WAL into checkpoints
- Deduplication uses Last-Write-Wins

## Adding a New Transformation

1. Create a folder under `pipeline/`
2. Name format: `{source-model-slug}/`
3. Create `README.md` with transformation spec
4. Update this index

## Related Documents

- [WAL Strategy](../wal-strategy.md) - Central WAL documentation
- [From-Model-to-Model ADR](../adr/from-model-to-model.md) - Transformation pattern
