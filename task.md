# Task: Screaming Architecture & Ordinance-to-Model Alignment (OMAP)

## Objective
Align the Python codebase with the Data Ordinance defined in `docs/_schema/ORDINANCE_ALIGNMENT.md`. Implement a hierarchical, type-safe pathing system using dot-notation and formalize the `Ordinant` protocol for all persistent models.

## Phase 1: Foundation (Type-Safe Ordinant Protocol)
- [x] **Define Ordinant Protocol**: Create `cocli/core/ordinant.py` defining the `Ordinant` protocol and collection `Literal` types.
    - `CollectionName = Literal["companies", "people", "wal"]`
    - `IndexName = Literal["google_maps_prospects", "target-tiles", "domains", "emails"]`
    - `QueueName = Literal["enrichment", "gm-details", "gm-list"]`
- [x] **Deterministic Pathing Logic**: Implement standardized sharding logic in `ordinant.py` to be shared across models.

## Phase 2: Hierarchical DataPaths (Dot-Notation)
- [x] **Refactor `DataPaths`**: Overhaul `cocli/core/paths.py` to return sub-path objects instead of raw strings/Paths for complex structures.
    - [x] `paths.campaign(slug: str) -> CampaignPaths`
    - [x] `paths.companies -> CollectionPaths`
    - [x] `paths.people -> CollectionPaths`
    - [x] `paths.wal -> WalPaths`
- [x] **Implement Sub-Path Objects**:
    - `CampaignPaths`: `.indexes`, `.queues`, `.exports`, `.config`.
    - `QueuePaths`: `.pending`, `.completed`, `.sideline`.
    - `CollectionPaths`: `.entry(slug: str) -> EntryPaths`.
- [x] **The `.ensure()` Method**: Add a method to all path objects that returns the `Path` after ensuring the directory exists, replacing boilerplate in `config.py`.

## Phase 3: Model Alignment
- [x] **Migrate Core Models**:
    - [x] `Company`: Implement `Ordinant`. Path: `data/companies/{slug}/`.
    - [x] `Person`: Implement `Ordinant`. Path: `data/people/{slug}/`.
    - [ ] `EnrichmentTask`: Formalize `Ordinant` implementation.
- [x] **Refactor Base Index**:
    - [x] `BaseIndexModel`: Update to use `Ordinant` for deterministic shard and file resolution.

## Phase 4: Config Simplification & Cleanup
- [x] **Deprecate Legacy Path Helpers**: Refactor `cocli/core/config.py` to remove redundant `get_*_dir` functions.
    - Example: `get_companies_dir()` becomes `paths.companies.ensure()`.
- [x] **Update Call Sites**: Audit the codebase and update all imports from `config.get_*_dir` to use the new `paths` hierarchy.

## Phase 5: Verification & Safety
- [ ] **Ordinance Validation**: Add a startup check that verifies the first record of a sync matches the expected `docs/_schema/` path.
- [x] **Tests**: Update `tests/test_paths.py` (or create it) to verify the new hierarchical pathing and `Ordinant` resolution.
