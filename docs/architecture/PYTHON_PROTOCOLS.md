# Architectural Decision: Python Protocols for Schema Evolution

## Context
As the Company CLI (cocli) expanded from a simple CRM to a multi-campaign platform, we encountered "Schema Evolution" challenges. Specifically, different campaigns required different metadata for similar entities (e.g., Sales Leads vs. Community Venues).

## The Problem
Using a single concrete model (like `GoogleMapsProspect`) for all use cases led to:
1.  **Model Bloat**: Adding optional fields for every new campaign made the model difficult to maintain.
2.  **Type Brittleness**: Code using `isinstance()` or `getattr()` to handle variations became prone to runtime errors.
3.  **DuckDB Join Failures**: SQL queries broke when columns expected by the Python model were missing from the underlying USV files.

## The Solution: Structural Subtyping (Protocols)
We have adopted **Python Protocols** (`typing.Protocol`) as the primary mechanism for interface definition and polymorphic behavior.

### Key Principles
1.  **The Rule of Two**: The moment code requires `isinstance()` checks or `getattr()` guards to handle two or more similar models, a `Protocol` MUST be implemented.
2.  **Interface over Implementation**: Services (like `search_service.py`) and UI components (like `CompanyDetail`) should type-hint against Protocols rather than concrete classes.
3.  **Narrow Base Models**: Establish a "Identity & Physicality" anchor (e.g., `GoogleMapsPlace`) that contains only the universal fields, and extend it for specific campaign needs.

### Benefits
-   **Stability**: DuckDB joins become schema-resilient by using the Protocol as the "Canonical Schema."
-   **Static Analysis**: `mypy` can catch missing attributes or type mismatches before they hit production.
-   **Flexibility**: New entity types can be added to the system without modifying existing business logic, as long as they implement the required Protocol methods.

## Implementation Standard
Every Protocol-based model hierarchy should include:
-   A **Base Model** (Pydantic) for shared fields.
-   A **Protocol** (@runtime_checkable) defining the public interface.
-   **Mock-Safe Validators**: Core types (like `PlaceID`) should handle `MagicMock` objects to prevent test-suite validation failures.

## Reference
See `cocli/models/campaigns/indexes/google_maps_place.py` for the reference implementation of `GoogleMapsPlaceProtocol`.
