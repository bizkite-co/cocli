# Issue: Implement Service Protocols for Application API

## Overview
Currently, the `cocli` Application API (defined in `cocli/application/services.py`) uses `Any` for its service injections. This prevents static analysis tools like `mypy` from verifying that the injected services match the expected interface. 

We will implement `typing.Protocol` (Structural Typing) to define formal interfaces for our core services, aligning the codebase with the "Screaming Architecture" documented in `docs/reference/api.md`.

## Proposed Change
Migrate the `ServiceContainer` from `Any` types to formal `Protocol` definitions.

### Example Protocol (Draft)
```python
from typing import Protocol, List, Dict, Any, Optional

class SearchServiceProvider(Protocol):
    def __call__(self, query: str, campaign_name: Optional[str] = None) -> List[Dict[str, Any]]:
        ...
```

## Tasks
- [ ] **Define Service Protocols**: Create `cocli/application/protocols.py` (or similar) to house the structural definitions for:
    - `SearchService` (Fuzzy search and template counts)
    - `CampaignService` (Campaign CRUD and state)
    - `WorkerService` (Scraper orchestration)
    - `ReportingService` (Audit and status)
- [ ] **Update ServiceContainer**: Replace `Any` type hints in `cocli/application/services.py` with the new Protocols.
- [ ] **Validate Implementations**: Ensure the concrete functions in `cocli/application/*.py` match the defined Protocol shapes.
- [ ] **Enhance Mocks**: Update `tests/conftest.py` to use these Protocols for more robust mocking.

## Benefits
- **Static Safety**: Catch "missing method" or "wrong argument" errors at lint-time (via `make lint`).
- **IDE Support**: Full autocomplete and type-checking for services inside the TUI and CLI.
- **Decoupling**: The UI depends on a *shape*, not a specific file, making it easier to swap implementations (e.g., swapping a Local search for an S3-backed search).

## Context Links
- **Documentation**: [docs/reference/api.md](docs/reference/api.md)
- **Current Entrypoint**: `cocli/application/services.py`
