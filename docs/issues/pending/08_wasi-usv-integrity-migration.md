# Task: WASI-Driven Data Integrity and Migrations

## Objective
Implement a distributed migration framework using WASI-based data services and content-addressable versioning.

## Requirements
- **WASI Data Service**: Create a WASI module for standardized USV Read/Write operations.
- **Service Hashing**: Generate a hash of the WASI binary and store it in `datapackage.json` under `cocli:wasi_hash`.
- **Migration Orchestration**:
    - Define a `MigrationTask` that includes the `Old_WASI_Hash`, `New_WASI_Hash`, and `Transformer_WASI`.
    - Deploy these tasks to PI workers.
    - Workers use the `Old_WASI` to read their local shards and `New_WASI` to write the results.
- **Verification**: Ensure the final `datapackage.json` is only updated once all local/remote shards pass the `cocli audit fs` check.

## Benefits
- Permanent field-level integrity via immutable code (WASM).
- Decentralized migrations (no massive centralized downloads).
- Transparent audit trail of which code created which data.
