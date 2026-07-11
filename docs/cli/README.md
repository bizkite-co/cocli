# CLI Structure

This directory contains the documentation for the cocli CLI command hierarchy.

## Implementation Status

- **Dumper:** `cocli audit cli --output docs/cli/actual_tree.txt`
- **Trigger:** `make cli-tree`

## Golden Snapshot (safety net)

A committed golden snapshot lives at `tests/goldens/cli_tree.txt` and is
asserted by `tests/test_cli_surface.py`. Any PR that changes the command
surface must update the golden in the same PR:

```bash
uv run cocli audit cli --output tests/goldens/cli_tree.txt
```

A parameterized `--help` smoke test in the same file also invokes every
leaf command to catch import/registration breakage.

## Structure

The CLI is built with `typer` and follows a nested subcommand structure.
The `actual_tree.txt` file is generated automatically to represent the current implemented structure.
