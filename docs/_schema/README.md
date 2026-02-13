# Cocli Data Ordinance & Synchronization Policy

This document defines the "Gold Standard" for how data is addressed, accessed, and propagated across the `cocli` ecosystem.

## 1. The Unified Coordinate Policy (UCP)
Every data element in `cocli` has a deterministic **Ordinant** (a universal-namespace path). 
`{COLLECTION} / {SLUG} / {QUADRANT} / {LEAF}`

### Verifiable Rules:
1.  **Identity is Path**: An object's `slug` must be the directory name.
2.  **Code-First Mapping**: Pydantic models must reflect the directory structure. 
    *   A `Company` model should contain a `notes: List[Note]` field.
    *   Saving the `Company` model should automatically distribute data to `{slug}/_index.md` and `{slug}/notes/*.md`.
3.  **Role-Based Access (RBA)**:
    *   `Collector`: Can write to `prospects/` and `scraped_data/`.
    *   `Enricher`: Can update `info/` and `website_data/`.
    *   `Editor`: Can update `notes/`, `meetings/`, and `contacts/`.
    *   `Admin`: Can modify `tags/` and `exclusions/`.

## 2. Propagation Strategy: "Leaf-First Sync"
Instead of bulk-syncing directories, `cocli` aims for **Atomic Delta Propagation**.

### Implementation Idioms:
*   **SyncThing / FreeNet Style**: Because every note is a unique file (`{timestamp}.md`), we avoid merge conflicts. New files are simply "announced" to the network.
*   **S3 Content-Addressing**: When a leaf node (e.g., a phone number) changes, only that specific ordinant's file is invalidated and re-uploaded.
*   **Wormhole Updates**: For TUI-to-Cloud propagation, we should prioritize **Immediate S3 Pushes** for user-generated content (Notes/Edits) to ensure other workers see the update in < 5 seconds.

## 3. Validation (Tests as Documentation)
Our documentation is validated via BDD features in `features/schema/`.
*   `Feature: Ordinant Resolution`: Asserts that `Note(company="actus").path` always equals `data/companies/actus/notes/...`.
*   `Feature: Role Enforcement`: Asserts that a `worker` role cannot overwrite a `note` file.
