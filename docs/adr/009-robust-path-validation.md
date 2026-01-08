# ADR 009: Robust Path Validation via Pydantic and Central Path Authority

## Status
Proposed (Phase 11 Implementation)

## Context
Ad-hoc path resolution using `Path("data/...")` or relative strings has caused recurring bugs where the system erroneously reports files as missing (returning `False` on `exists()`) when the actual issue is an incorrectly resolved base directory or a broken symlink. In a distributed system, this leads to duplicate work and data corruption.

## Decision
We will enforce a strict "Central Path Authority" pattern and use Pydantic models to validate paths before they are used in any business logic.

### Key Implementation Details

#### 1. `PathModel` (Pydantic)
Every critical data directory will be represented by a Pydantic model that:
- Resolves symlinks automatically during initialization.
- Validates that the **Base Directory** exists.
- Throws a `ConfigError` or `PathResolutionError` if the base is missing, rather than allowing the application to proceed with incorrect assumptions.

#### 2. Central Registry in `cocli/core/config.py`
We will move all path-generating logic (e.g., `get_scraped_areas_index_dir()`) into a single registry. Ad-hoc path construction in `commands/` or `scrapers/` will be strictly forbidden by linting rules.

#### 3. Absolute Path Enforcement
All paths used by the system will be converted to **Absolute Resolved Paths** immediately upon resolution. This eliminates "Current Working Directory" (CWD) ambiguity.

## Implications

### Reliability
- **Fail-Fast:** The application will crash during initialization if the data directory is not correctly mounted or symlinked.
- **Deduplication Integrity:** If the system cannot see the `scraped-tiles` index, it will **refuse to enqueue**, preventing duplicate work.

### Development Workflow
- **Linter Integration:** We can add custom Ruff rules to flag `Path("data/...")` usage outside of `core/config.py`.
- **Testable Paths:** We can write unit tests that verify path resolution across different operating systems (Linux vs. Mac).

## Implementation Baby Steps
1. Create `cocli/core/paths.py` with the base `ValidatedPath` model.
2. Update `cocli/core/config.py` to return validated path objects.
3. Refactor `queue-mission` to use these validated objects.
