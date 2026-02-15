# Ordinance-to-Model Alignment Policy (OMAP)

This policy ensures that the Python codebase is a "Screaming Architecture" mirror of the Data Ordinance.

## 1. The Mirror Rule
The directory structure in `cocli/models/` must match the directory structure in `data/` (as documented in `docs/_schema/data-root/`).

### Proposed Hierarchy:
*   `cocli/models/campaigns/index/` -> `data/campaigns/{name}/indexes/`
*   `cocli/models/campaigns/queue/` -> `data/campaigns/{name}/queues/`
*   `cocli/models/companies/` -> `data/companies/`
*   `cocli/models/people/` -> `data/people/`

## 2. Type-Safe Pathing
To eliminate "String-ly Typed" fragility, we use Python `Literal` types for all standardized collection and leaf names.

### Implementation Idiom:
```python
from typing import Literal

# These are the "Known Universe" of collection names
IndexName = Literal["google_maps_prospects", "target-tiles", "domains"]
QueueName = Literal["enrichment", "gm-details", "gm-list"]

class CampaignPaths:
    def queue(self, name: QueueName) -> QueuePaths:
        # IDE will autocomplete 'enrichment', 'gm-details', etc.
        # MyPy will error if you type 'enritchment'
```

## 3. The "Ordinant" Protocol
Every model that represents a stored file must implement the `Ordinant` protocol, which provides deterministic path resolution.

```python
class Ordinant(Protocol):
    def get_local_path(self) -> Path: ...
    def get_remote_key(self) -> str: ...
    def get_shard(self) -> str: ...
```

## 4. TUI Discovery
The TUI must not "guess" paths. It must use the `ModelRegistry` to discover available models and then use the `paths` utility to discover which instances (campaigns/companies) exist on disk.

## 5. Migration Safety
Before any bulk write (e.g., `sync-index`), the system must:
1.  Resolve the `Ordinant` for the first record.
2.  Verify the path matches the `docs/_schema/`.
3.  Fail-fast if there is a mismatch.
