# cocli repository instructions

## Commands

The project uses Python 3.12 and `uv`. Install the development and optional full/TUI dependencies with:

```bash
make install
```

Use the Makefile targets as the canonical checks:

```bash
make lint                                      # Ruff --fix, strict mypy, import-linter
make test                                      # non-TUI pytest suite; runs lint first
make test-unit                                 # excludes TUI, E2E, and data tests
make test-tui                                  # TUI tests
make test-tui-integration                      # navigation integration test
make test-file FILE=tests/unit/test_dfq.py    # one test file
PYTHONPATH=. .venv/bin/pytest tests/unit/test_dfq.py -k test_name -v
make build
```

`make test` and `make lint` are incremental through `taskhash`; invoke the underlying targeted
`pytest` command when a changed test must run regardless of the cache. E2E tests are separate
(`make test-e2e`) and require 1Password access. Install Chromium for browser work with
`make playwright-install`.

Run the CLI as `uv run cocli ...`; `cocli/main.py` wires the command tree. `make dev` starts the
Textual TUI with file watching.

## Architecture

- **CLI adapters:** `cocli/commands/` defines Typer commands and command groups. Keep this layer
  thin: parse options, select a campaign, call a service, and present results.
- **Product logic:** `cocli/application/` holds domain orchestration (companies, campaigns,
  enrichment, workers, reporting). `cocli/services/` holds low-level infrastructure drivers such
  as SSH/Docker cluster operations, deployment, S3/WAL, and queue staging.
- **Reusable substrate:** `cocli/core/` contains campaign configuration, path grammar, queue/WAL,
  indexes, claims/leases, and audit/schema primitives. It is the extraction boundary for the
  `stations` file-path-queue library; do not treat `application/` or `services/` as candidates for
  that library.
- **Data pipeline:** Commands should be explicit Pydantic model-to-model transformations. Name
  transformations after their source and destination where practical (for example,
  `google-maps-cache to-company-files`) and keep intermediate states traceable rather than
  folding multiple pipeline stages into one command.

Most operations are campaign-scoped. Resolve a campaign through `--campaign`, then the configured
default; a campaign owns its data root and AWS profile. Use `COCLI_DATA_HOME` only when deliberately
overriding the data root.

The distributed discovery/enrichment pipeline uses typed filesystem/S3 queues: workers claim work
with leases and only acknowledge after producing a validated result/receipt. Do not bypass queue
protocols with direct state-file mutations. Large index data is headerless, unit-separated
(`\x1f`) `.usv`; keep its `datapackage.json` Frictionless schemas synchronized with any format
change. Paths mirror across local, Raspberry Pi, and S3 storage, and records retain identity
lineage from discovery through enrichment.

## Repository-specific conventions

- Models crossing transformation boundaries are Pydantic models. For behavior shared by two or
  more related models, define and consume a narrow `typing.Protocol` rather than adding
  `isinstance()`/`getattr()` branches. Protocol-based core identifiers must tolerate `MagicMock`
  values used by tests.
- Strict mypy is enabled. Type all function signatures and preserve the import layering enforced
  by `lint-imports`: `core` and `models` must not import `application`, `services`, `commands`, or
  `tui`; `scrapers` and `tui` must not import `commands`; commands are leaf adapters.
- Google Maps detail scraping must run on residential Raspberry Pi workers. AWS Fargate is only
  suitable for general website enrichment because Google Maps blocks Fargate IP ranges.
- TUI work belongs under `cocli/tui/` and should call application services, never commands.
  `COCLI_IMAGE_BACKEND=halfcell|unicode|tgp|none` is available for terminal-image troubleshooting;
  preserve the rendered-output regression coverage in
  `tests/tui/test_screenshot_image_backend.py`.

## References

- `docs/adr/from-model-to-model.md` — transformation model
- `docs/cli/target-tree.md` — command grouping and layer-placement rules
- `docs/data-management/directory-data-structure.md` — campaign namespace and USV schema rules
- `docs/architecture/PYTHON_PROTOCOLS.md` — protocol standard for schema evolution
