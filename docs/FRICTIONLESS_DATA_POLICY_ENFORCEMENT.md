# Frictionless Data Policy Enforcement (FDPE) for Cocli

## Core Mandate
All tabular data in `cocli` is subject to the **frictionless-data-policy-enforcement** (FDPE). This policy establishes `datapackage.json` as the immutable authority for data structure, ensuring performance and compatibility with standard CLI tools.

## The Pillars of FDPE

### 1. The Cocli USV Format
Cocli uses a specialized Unit Separated Value (USV) format designed for high performance and CLI interoperability:
- **Field Delimiter:** `\x1f` (Unit Separator).
- **Record Separator:** `\n` (Newline). 
- **Rationale:** Using `\n` instead of the USV-standard `\x1e` ensures that datasets work seamlessly with `grep`, `sed`, `awk`, `wc`, and other standard Unix utilities while maintaining the power of non-printable delimiters.

### 2. Headerless Data Streams (The Default)
Standard datasets (Bulk Indices, Checkpoints, WAL journals) MUST NOT contain headers. The first line of the file is the first record of data. Headers are considered noise and are forbidden in bulk stores.

### 3. Model-to-Schema Authority (BaseIndexModel)
The `cocli.models.campaigns.indexes.base.BaseIndexModel` is the runtime authority for schema generation.
- **Dynamic Generation:** Every index model must inherit from `BaseIndexModel`. The model's Pydantic fields define the column order and technical names in the `datapackage.json`.
- **Versioning:** The `SCHEMA_VERSION` ClassVar on the model is the source of truth for the dataset version. Any change to field order or types must be accompanied by a version bump.
- **Self-Healing:** Managers must call `write_datapackage()` upon initialization to ensure the `datapackage.json` on disk is perfectly aligned with the Python model in the current release.

### 4. Schema Authority
For headerless datasets, the `datapackage.json` in the index directory is the SOLE authority for:
- Column sequence and field names.
- Data type constraints (string, integer, number, datetime, boolean).
- Dialect definitions.

### 5. Systematic Enforcement in DuckDB
Loading logic must never rely on "auto-detection." It must:
- Extract field names/types from `datapackage.json`.
- Map the headerless stream explicitly to these names.
- Use `TRY_CAST` to enforce types and prevent numeric/rating data from being treated as strings.

## Exceptions to the "No Header" Rule

### File-per-Object Data Stores
In cases where data is stored as individual files per entity (e.g., `data/companies/{slug}/enrichments/google_maps.usv`), a **Header is REQUIRED**.
- **Rationale:** For thousands of small files distributed across the filesystem, a central `datapackage.json` is impractical and fragile. In this "distributed" mode, each file must be self-describing via a header line using the `\x1f` delimiter.

## Code Reference
All modules that read, write, or query tabular datasets must include the following reference at the top of the file:
`# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)`
