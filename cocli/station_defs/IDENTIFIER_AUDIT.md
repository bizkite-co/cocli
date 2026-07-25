# Identifier-segment audit (decision 0010 §4a)

Rule: station path segments MUST be valid identifier segments in mainstream
module systems — lowercase, `[a-z0-9_-]`, with `-` → `_` projection for
Python packages.

| Data path segment | Code module projection | Status |
| :--- | :--- | :--- |
| `campaigns` | `campaigns/` | OK |
| `indexes` | `indexes/` | OK |
| `emails` | `emails.py` | OK |
| `google_maps_prospects` | `google_maps_prospects.py` | OK (`_`) |
| `scraped-tiles` | `scraped_tiles` (if defined) | OK with `-`→`_` |
| `queues` | `queues/` | OK |
| `gm-list` | `gm_list` | OK with `-`→`_` |
| `gm-details` | `gm_details` | OK |
| `to-call` | `to_call` | OK |
| `discovery-gen` | `discovery_gen` | OK |
| `map-tile` | `map_tile` | OK |
| `wal` | `wal/` | OK |
| `inbox` / `shards` / `pending` | segment *types* (values on disk) | values not packages |

No blocking violations for the first mirror set. Queue identity enums already
use hyphenated *data* names; code packages use underscores.

## Segment combinators (0010 §3)

Phases and shards are **not** hard-coded global scenarios. At station
declaration time, each `StationDecl` passes its own:

- `phases("pending", "completed", …)` — names for *that* station
- `shard_by_hash(n)` / `shard_by_prefix(k)` — width/params for *that* station
- `partition_by_day_of_month(ttl_days=…)` when used

Runtime values (`pending/`, shard `a7`) remain on disk only. See
`stations.segments` and tests in the stations package.
