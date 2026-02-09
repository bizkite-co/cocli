# Cocli Filesystem & S3 Schema Specification

This directory uses the filesystem itself to document the expected structure of data across different environments (Local, S3, RPi). 

## Structure
Each sub-directory mirrors a real environment. The contents of these directories define the "Gold Standard" for paths, file naming, and formats.

- `local/`: Standard structure for local development and campaign data.
- `s3-bucket/`: Standard namespace for the campaign S3 data bucket.
- `rpi-worker/`: Structure inside the Raspberry Pi Docker containers.

## Validation & Testing
This schema is designed to be machine-verifiable. 

1. **Path Checks**: Test suites can use these directories as "gold standard" templates to ensure `cocli` code creates directories and files in the correct namespaces.
2. **Schema Matching**: Data index files (like USV or JSON) should match the schemas defined in these folders.
3. **Environment Audit**: A script can walk a real environment (like an RPi or S3 bucket) and flag any paths that do not exist in this schema tree, helping identify "sloppy" or legacy file handling.

## Maintenance
When implementing a new feature that adds a new index, queue, or configuration node:
1. Create the corresponding directory in `docs/_schema/`.
2. Add a `README.md` explaining why it exists.
3. (Optional) Add a schema or example if the format is new.

## Legend
- `README.md`: Describes the purpose of a directory or node.
- `*.schema.json`: Frictionless Data or JSON Schema defining the file format.
- `example.*`: A valid example file showing the expected content.
