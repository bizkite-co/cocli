# Task: Screaming Architecture & Ordinance-to-Model Alignment (OMAP)

## Objective
Align the Python codebase with the Data Ordinance defined in `docs/_schema/ORDINANCE_ALIGNMENT.md`. Implement a hierarchical, type-safe pathing system using dot-notation and formalize the `Ordinant` protocol for all persistent models.

## Phase 1: Foundation (Type-Safe Ordinant Protocol)
- [ ] **Define Ordinant Protocol**: Create `cocli/core/ordinant.py` defining the `Ordinant` protocol and collection `Literal` types.
    - `CollectionName = Literal["companies", "people", "wal"]`
    - `IndexName = Literal["google_maps_prospects", "target-tiles", "domains", "emails"]`
    - `QueueName = Literal["enrichment", "gm-details", "gm-list"]`
- [ ] **Deterministic Pathing Logic**: Implement standardized sharding logic in `ordinant.py` to be shared across models.

## Phase 2: Hierarchical DataPaths (Dot-Notation)
- [ ] **Refactor `DataPaths`**: Overhaul `cocli/core/paths.py` to return sub-path objects instead of raw strings/Paths for complex structures.
    - [ ] `paths.campaign(slug: str) -> CampaignPaths`
    - [ ] `paths.companies -> CollectionPaths`
    - [ ] `paths.people -> CollectionPaths`
    - [ ] `paths.wal -> WalPaths`
- [ ] **Implement Sub-Path Objects**:
    - `CampaignPaths`: `.indexes`, `.queues`, `.exports`, `.config`.
    - `QueuePaths`: `.pending`, `.completed`, `.sideline`.
    - `CollectionPaths`: `.entry(slug: str) -> EntryPaths`.
- [ ] **The `.ensure()` Method**: Add a method to all path objects that returns the `Path` after ensuring the directory exists, replacing boilerplate in `config.py`.

## Phase 3: Model Alignment
- [ ] **Migrate Core Models**:
    - [ ] `Company`: Implement `Ordinant`. Path: `data/companies/{slug}/`.
    - [ ] `Person`: Implement `Ordinant`. Path: `data/people/{slug}/`.
    - [ ] `EnrichmentTask`: Formalize `Ordinant` implementation.
- [ ] **Refactor Base Index**:
    - [ ] `BaseIndexModel`: Update to use `Ordinant` for deterministic shard and file resolution.

## Phase 4: Config Simplification & Cleanup
- [ ] **Deprecate Legacy Path Helpers**: Refactor `cocli/core/config.py` to remove redundant `get_*_dir` functions.
    - Example: `get_companies_dir()` becomes `paths.companies.ensure()`.
- [ ] **Update Call Sites**: Audit the codebase and update all imports from `config.get_*_dir` to use the new `paths` hierarchy.

## Phase 5: Verification & Safety
- [ ] **Ordinance Validation**: Add a startup check that verifies the first record of a sync matches the expected `docs/_schema/` path.
- [ ] **Tests**: Update `tests/test_paths.py` (or create it) to verify the new hierarchical pathing and `Ordinant` resolution.
