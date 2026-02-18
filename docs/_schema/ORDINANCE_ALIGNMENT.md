# Ordinance-to-Model Alignment Policy (OMAP)

This policy ensures that the Python codebase is a "Screaming Architecture" mirror of the Data Ordinance.

## 1. The Mirror Rule
The directory structure in `cocli/models/` and the path resolution in `cocli/core/paths.py` must match the physical directory structure in `data/`.

### Implemented Hierarchy:
*   `paths.campaign(slug).indexes` -> `data/campaigns/{slug}/indexes/`
*   `paths.campaign(slug).queues` -> `data/campaigns/{slug}/queues/`
*   `paths.companies` -> `data/companies/`
*   `paths.people` -> `data/people/`
*   `paths.wal` -> `data/wal/`

## 2. Type-Safe Pathing
To eliminate "String-ly Typed" fragility, we use Python `Literal` and `Union` types for all standardized collection, index, and queue names in `cocli/core/ordinant.py`.

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
