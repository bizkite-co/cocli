# Universal Data Namespace (data-root)

> **Status note (2026-07-15):** this shadow-tree schema is the earliest attempt at the
> "logical namespace as file path" idea that later became the `stations` pattern
> (`~/repos/stations`). Some subtrees here have drifted from the real data root — treat as
> historical prior art, not a currently-verified spec.
>
> **`cocli audit fs` (the validator against this schema) is slow/hangs on the real data
> root — this is a known bug, not expected behavior.** Root cause: `--campaign` only
> scopes the `campaigns/` subtree; global collections (`indexes/`, `people/`, `cache/`,
> `wal/`) are walked in full regardless. `_audit_usv_rows` (in
> `cocli/core/audit/fs_auditor.py`) also re-opens and re-parses the nearest
> `datapackage.json` for every single sibling `.usv` file with no per-directory caching —
> on `indexes/domains/manifests/` (13k+ small files) this alone makes a full run
> impractical. Until fixed, narrow scope deliberately: run `cocli audit fs` against a
> single subtree at a time (e.g. point `--output` at a copy with only the directory you
> care about, or invoke `FsAuditor` directly with a narrower `root=`) rather than the
> whole data root.
>
> USV row/column-content validation duplicates work that already has a proper home:
> `cocli/utils/duckdb_utils.py`'s `load_usv_to_duckdb` (used by
> `scripts/audit_prospect_quality.py`) loads a `.usv` against its `datapackage.json` via
> DuckDB — that's the right tool for content-level checks. `_audit_usv_rows`'s manual
> per-line split-and-count should be rerouted there rather than reimplemented in Python.

This schema defines the shared structure used across all Cocli environments. The contents of this directory are mirrored 1:1 between local filesystems and S3.

## Environment Mapping
- **S3**: `s3://cocli-data-{campaign}/`
- **Local (Ubuntu)**: `/home/{username}/repos/company-cli/data/` (via symlink)
- **Local (Data Home)**: `/home/{username}/.local/share/cocli_data/`
- **RPi Cluster**: `/app/data/`

## Conventions
1. **No Headers**: Sharded data files (.usv) OMIT headers. Type and field names are defined in the co-located `datapackage.json`.
2. **Deterministic Sharding**:
   - **PlaceID**: `{shard}/ChIJ-{rest}.usv` where shard is `place_id[5]`.
   - **Geo**: `{shard}/{lat}/{lon}/{phrase}.usv` where shard is `latitude[0]`.
3. **Mirrored Structure**: Any file added to `pending/` or `completed/` must follow the same path hierarchy regardless of the storage provider.
