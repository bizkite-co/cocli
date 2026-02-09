# Universal Data Namespace (data-root)

This schema defines the shared structure used across all Cocli environments. The contents of this directory are mirrored 1:1 between local filesystems and S3.

## Environment Mapping
- **S3**: `s3://cocli-data-{campaign}/`
- **Local (Ubuntu)**: `/home/mstouffer/repos/company-cli/data/` (via symlink)
- **Local (Data Home)**: `/home/mstouffer/.local/share/cocli_data/`
- **RPi Cluster**: `/app/data/`

## Conventions
1. **No Headers**: Sharded data files (.usv) OMIT headers. Type and field names are defined in the co-located `datapackage.json`.
2. **Deterministic Sharding**:
   - **PlaceID**: `{shard}/ChIJ-{rest}.usv` where shard is `place_id[5]`.
   - **Geo**: `{shard}/{lat}/{lon}/{phrase}.usv` where shard is `latitude[0]`.
3. **Mirrored Structure**: Any file added to `pending/` or `completed/` must follow the same path hierarchy regardless of the storage provider.
