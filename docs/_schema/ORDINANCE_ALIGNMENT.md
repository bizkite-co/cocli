# Ordinance-to-Model Alignment Policy (OMAP)

This policy ensures that the Python codebase is a "Screaming Architecture" mirror of the Data Ordinance.

## 1. The Mirror Rule
The directory structure in `cocli/models/` and the path resolution in `cocli/core/paths.py` must match the physical directory structure in `data/`.

### Implemented Hierarchy:
*   `paths.campaign(slug).indexes` -> `data/campaigns/{slug}/indexes/`
*   `paths.campaign(slug).queues` -> `data/campaigns/{slug}/queues/`
*   `paths.campaign(slug).exports` -> `data/campaigns/{slug}/exports/`
*   `paths.companies` -> `data/companies/`
*   `paths.people` -> `data/people/`
*   `paths.wal` -> `data/wal/`

## 2. Type-Safe Pathing
To eliminate "String-ly Typed" fragility, we use Python `Literal` and `Union` types for all standardized collection, index, and queue names in `cocli/core/ordinant.py`.

### Standardized Identifiers:
*   **CollectionName**: `companies`, `people`, `wal`, `tasks`
*   **IndexName**: `google_maps_prospects`, `target-tiles`, `domains`, `emails`
*   **QueueName**: `enrichment`, `gm-details`, `gm-list`, `gm-scrape`

### Implementation Idiom:
```python
from cocli.core.paths import paths

# Dot-notation provides IDE autocomplete and MyPy validation
queue_path = paths.campaign("turboship").queue("enrichment").pending
# Returns: Path("data/campaigns/turboship/queues/enrichment/pending")

# Use .ensure() to create the leaf directory if missing
idx_dir = paths.campaign("roadmap").index("emails").ensure()
```

## 3. The "Ordinant" Protocol
Every model that represents a stored file/directory must implement the `Ordinant` protocol defined in `cocli/core/ordinant.py`.

```python
class Ordinant(Protocol):
    def get_local_path(self) -> Path: ...
    def get_remote_key(self) -> str: ...
    def get_shard_id(self) -> str: ...
    
    @property
    def collection(self) -> CollectionName | IndexName | QueueName: ...
```

### Deterministic Sharding Strategies:
*   **place_id**: Uses the 6th character of the Google Place ID (e.g., `data/companies/a/`).
*   **domain**: Returns a 2-character hex shard (00-ff) based on the SHA256 of the domain.
*   **geo**: Uses the first character of the latitude.
*   **geo_tile**: Shards by the integer part of the latitude (e.g., `32`, `40`).

### Core Ordinants:
*   **Company**: `data/companies/{slug}/`
*   **Person**: `data/people/{slug}/`
*   **EnrichmentTask**: `data/campaigns/{campaign}/queues/enrichment/pending/{shard}/{domain}/`
*   **GmItemTask**: `data/campaigns/{campaign}/queues/gm-details/pending/{shard}/{place_id}/`
*   **ScrapeTask**: `data/campaigns/{campaign}/queues/gm-list/pending/{shard}/{lat}/{lon}/`

## 4. TUI Discovery
The TUI must not "guess" paths or construct them via manual string joining. It must use the `paths` authority to resolve paths for any model instance.

Example from `CompanyDetail`:
```python
# GOOD: Using OMAP Authority
path = paths.companies.entry(self.slug) / "_index.md"

# BAD: String-ly Typed pathing
path = Path("data/companies") / self.slug / "_index.md"
```

## 5. Migration Safety
Before any bulk write or sync operation, the system should:
1.  Resolve the `Ordinant` for the first record.
2.  Verify the path matches the Data Ordinance schema.
3.  Fail-fast if there is an architecture violation (e.g., "Naked" files in index roots).
