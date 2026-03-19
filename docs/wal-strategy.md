# WAL Strategy

## The Problem: Concurrent Writes to Shared Index

In a distributed scraping environment, multiple worker nodes (Raspberry Pis, cloud workers) need to write results to a shared index. Direct concurrent writes to a single file cause:

- **File locks and contention**
- **Data corruption**
- **Lost updates**

## The Solution: Write-Ahead Log (WAL) Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                    Distributed Workers                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                   │
│  │  Worker  │   │  Worker  │   │  Worker  │                   │
│  │    1     │   │    2     │   │    3     │                   │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘                   │
│       │              │              │                            │
│       ▼              ▼              ▼                            │
│  ┌─────────────────────────────────────────┐                    │
│  │           WAL Append-Only Files           │                    │
│  │  wal/YYYYMMDD_worker1.usv              │                    │
│  │  wal/YYYYMMDD_worker2.usv              │                    │
│  │  wal/YYYYMMDD_worker3.usv              │                    │
│  └─────────────────────────────────────────┘                    │
│                      │                                          │
│                      ▼                                          │
│              ┌───────────────┐                                  │
│              │  Compaction   │                                  │
│              │   (WASI)      │                                  │
│              └───────┬───────┘                                  │
│                      │                                          │
│                      ▼                                          │
│        ┌─────────────────────────┐                             │
│        │  Deduplicated Index      │                             │
│        │  indexes/checkpoint.usv  │                             │
│        └─────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## WAL Properties

### 1. Append-Only
Workers only append to their dedicated WAL file. No reads or updates.

### 2. One File Per Node Per Day
```
wal/
├── 20260318_worker1.usv
├── 20260318_worker2.usv
├── 20260318_worker3.usv
└── 20260319_worker1.usv
```

### 3. Compaction Merges and Deduplicates
- Reads all WAL files
- Deduplicates by primary key (e.g., `place_id`)
- Uses Last-Write-Wins (LWW) based on timestamp
- Writes to consolidated checkpoint

### 4. WAL Files Are Deleted After Compaction
Compaction removes source WAL files to:
- Reduce disk usage
- Speed up future compactions
- Prevent double-compaction

## Per-Index WALs

Each data index has its own WAL pattern:

| Index | WAL Source | Checkpoint | Notes |
|-------|-----------|------------|-------|
| `gm-list` | GmListResult USVs | GmListCheckpoint | Pre-compacted from PI scrapers |
| `gm-details` | GmDetailsResult USVs | GmDetailsCheckpoint | Detail scrapes |
| `enrichment` | EnrichmentResult USVs | EnrichmentCheckpoint | Website enrichment |

## Special Case: GmListResult Pre-Compaction

The GmList scraper is a high-performance innovation that collects more data than GmDetails in a single pass. Unlike traditional WAL files:

1. **KEEP GmListResult files forever** - valuable for tracing/debugging
2. **Do NOT delete after compaction** - only use as source for compaction
3. **Treat as pre-compacted WAL** - dense, deduplicated per file

```
queues/gm-list/completed/results/
├── 2/25.0/-80.7/financial-advisor.usv    ← Keep forever
├── 2/25.0/-80.7/wealth-manager.usv       ← Keep forever
└── ...
```

## Compaction Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  GmListResult  │     │   WAL Files     │     │ Other Sources   │
│   (keep!)      │     │   (delete)      │     │                 │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         ▼                      ▼                       ▼
┌────────────────────────────────────────────────────────────┐
│                     DuckDB Compaction                        │
│  - Load all sources                                         │
│  - Deduplicate by place_id                                  │
│  - Last-Write-Wins conflict resolution                      │
│  - Sort by place_id                                         │
└────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  prospects.checkpoint   │
              │       .usv             │
              └────────────────────────┘
```

## Related Documents

- [Pipeline Transformations](./pipeline/) - From-model-to-model specs
- [GmList to Prospect](./pipeline/gm-list/to-google-maps-prospect/) - Specific transformation
