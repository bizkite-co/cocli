# CLI Structure

This directory contains the documentation for the cocli CLI command hierarchy.

## Implementation Status

- **Dumper:** `cocli audit cli --output docs/cli/actual_tree.txt`
- **Trigger:** `make cli-tree`

## Structure

The CLI is built with `typer` and follows a nested subcommand structure.
The `actual_tree.txt` file is generated automatically to represent the current implemented structure.
