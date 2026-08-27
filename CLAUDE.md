# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**cocli** is a Python CLI tool for managing a plain-text CRM system. It enables importing, querying, enriching, and managing company and person data while supporting distributed scraping across multiple worker types (Raspberry Pi, AWS Fargate, local).

**Core stack:**
- Python 3.9+, managed with `uv` (faster pip replacement)
- Typer for CLI framework with subcommand architecture
- Pydantic for data validation and models
- Pytest + pytest-bdd for BDD-style testing
- Mypy (strict mode) + Ruff for type checking and linting
- Playwright for web automation/scraping
- Textual for terminal UI (TUI)
- FastAPI + Uvicorn for enrichment services

## Getting Started

```bash
# Install dependencies (creates .venv)
make install

# Run any cocli command
uv run cocli --help
# Or after activating: source .venv/bin/activate && cocli --help

# Run tests
make test

# Run specific test file
make test-file FILE=tests/test_example.py

# Type check and lint (incremental with caching)
make lint

# Build distributables
make build

# Run TUI in dev mode with auto-reload
make dev
```

## Architecture and Key Patterns

### "From-Model-to-Model" Transformation (ADR-001)

The core philosophy: treat every CLI command as an explicit data transformation from one Pydantic model to another. This ensures:
- Clear, composable logic
- Testable business logic independent of CLI
- Explicit data flows

See `docs/adr/from-model-to-model.md` for details.

### Directory Structure

```
cocli/
├── main.py                # Entry point, registers all command groups
├── commands/              # Thin Typer adapters (leaf layer; no business logic)
│   ├── enrich.py
│   ├── audit.py
│   ├── query.py
│   ├── companies.py
│   ├── data.py
│   └── campaign/
├── core/                  # Substrate primitives (queue/WAL/index, config, paths)
│   ├── config.py          # Campaign/environment configuration
│   ├── paths.py           # Data directory paths
│   ├── models.py          # Shared Pydantic models
│   ├── bootstrap.py       # Environment initialization
│   ├── cache.py           # Website/domain caching
│   ├── queue/             # Filesystem/S3 queue + claim/lease protocol
│   └── audit/             # Schema validation and auditing
├── application/           # Domain/orchestration services (product-specific)
├── services/              # Low-level infra drivers: SSH, Docker, S3, WAL ops
├── scrapers/              # Web scrapers (Google Maps, general sites)
├── enrichment/            # Data enrichment services
├── importers/             # CSV/data importers
├── models/                # Domain-specific Pydantic models
├── compilers/             # Data compilation/indexing
├── renderers/             # Output formatters (KML, CSV, etc.)
├── tui/                   # Textual TUI implementation
├── web/                   # FastAPI enrichment service
└── utils/                 # Utilities (formatting, file ops, etc.)
```

### Three-tier layering (do not collapse these axes)

Two orthogonal boundaries — do not treat them as one:

**Axis 1 — library extraction (stations substrate vs cocli product)**

| Layer | Role | Library extraction? |
| :--- | :--- | :--- |
| `cocli/core/` | Queue, WAL, index, claim/lease, path grammar, schema/audit machinery | **Yes** — candidates for the reusable stations/file-path-queue library |
| `cocli/application/` + `cocli/services/` | Everything product-specific to the CRM/ops platform | **No** — stays in cocli regardless of which of those two dirs a module lives in |

**Axis 2 — intra-product split (only among non-extraction code)**

| Layer | Role | Examples |
| :--- | :--- | :--- |
| `cocli/application/` | Domain and orchestration services | MeetingService, TaskService, WorkerService, CompanyService |
| `cocli/services/` | Low-level infrastructure drivers | ClusterService (SSH/Docker on Pi nodes), S3/WAL drivers, deployment helpers |
| `cocli/commands/` | Thin CLI adapters over application/services | Typer option parsing, exit codes, user-facing messages |

`application/` vs `services/` is orchestration-vs-infra-driver *inside* cocli. It is not the
stations extraction cut line. Placing `ClusterService` under `services/` (SSH + docker exec)
follows Axis 2 correctly; it was never an extraction candidate. When in doubt: if it is typed
path-queue / WAL / index substrate, it belongs in `core/`; if it is cocli product logic, choose
`application/` (domain) or `services/` (infra driver) — never invent a third story about
extraction from those two.

Enforced by import-linter contracts in `pyproject.toml` (`core`/`models` must not import
`application`, `services`, `commands`, or `tui`). Detail: `docs/cli/target-tree.md`.

### Campaign Configuration

Commands operate in the context of a **campaign** (a named workspace with its own data directory and AWS profile). Configure in `cocli_config.toml`:

```toml
[campaigns.my-campaign]
data_home = "/path/to/data"
aws = { profile = "my-profile", region = "us-east-1" }
```

Campaigns are resolved in order:
1. `--campaign` CLI flag
2. Default campaign from config
3. Error if neither exists

### Frictionless Data Standards

Data integrity is enforced via Frictionless Data schemas:
- Sharded `.usv` files (headerless, using `\x1f` UNIT_SEP delimiter)
- Schemas defined in `datapackage.json`
- Validation via `scripts/audit_*.py` and `cocli audit fs` commands
- Identity traceability from Discovery → Enrichment

See `docs/data-management/DIRECTORY-DATA-STRUCTURE.md` and `docs/_schema/traceability.md`.

### Known Issues

**AWS Fargate + Google Maps Scraping:** Google Maps conclusively blocks Fargate IP ranges. Use Raspberry Pi workers for Google Maps detail tasks; Fargate is suitable for general website enrichment only.

**Tailscale dependency (Pi cluster LAN sync):** the Pi-to-dev-machine background file sync (`rsync --daemon` over `tailscale0`, replacing periodic full-tree `rsync` pulls for `pending/`/`completed/` queue state - see task-agent ticket `set-up-lsyncd-push-based-lan-sync-from-pi-nodes-to-dev-machine-sandboxed-via-rrsync`) depends on Tailscale for NAT traversal, since dev machines behind WSL2/home-router NAT aren't otherwise reachable from the Pi cluster's LAN. Tailscale's free tier caps devices/users - if that becomes a real constraint, `cocli sync pi-results` (S3-independent, SSH+rsync PULL, no Tailscale involved) remains available with no code changes for existing pull-based sync/audit tooling, but the rsync-daemon push path itself would need to be explicitly disabled - it isn't behind a feature flag.

## Common Development Tasks

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# E2E tests (requires 1Password CLI)
make test-e2e

# TUI integration tests
make test-tui-integration

# Single test file
make test-file FILE=tests/test_audit.py

# Run with pytest directly
pytest tests/ -k "test_name" -v
```

**BDD Testing:** Test specs are in `.feature` files (Gherkin syntax); implementations are step definitions in `tests/test_*.py` using `pytest-bdd`.

### Debugging

- **VSCode launch configs** in `.vscode/launch.json` (e.g., "Python: cocli import-data Debug")
- **TUI log:** `tail -f ~/.local/share/cocli/logs/tui.log`
- **Latest log:** `make logf` or `make logname`
- **Mypy daemon:** `mise run mypy-daemon-start` (faster iteration)

### Type Checking and Linting

```bash
# Lint + type check (incremental)
make lint

# Ruff check/fix
ruff check . --fix

# Mypy strict mode
mypy --config-file pyproject.toml .
```

**Strict Mypy enabled.** Type every function parameter and return. See `pyproject.toml` for mypy config (disables for `website_cache`, `campaign_app`, `company_detail`).

## Key Files to Know

- **`pyproject.toml`**: Dependencies, entry points, build config, mypy/ruff settings
- **`Makefile`**: Development tasks (install, test, lint, build, commit, audit commands)
- `.mise.toml`: Tool versions (Python 3.12) and preset tasks
- `.env`: Environment overrides (e.g., `COCLI_CAMPAIGN`, `OP_SERVICE_ACCOUNT_TOKEN`)
- `cocli_config.toml`: Campaign definitions and AWS profiles
- `VERSION`: Semantic version for the package

## Data and Environment

- **Default data home:** `~/.local/share/cocli/` (XDG Base Directory Spec)
- **Override:** Set `COCLI_DATA_HOME` environment variable
- **Environment modes:** `DEV` (local), `UAT` (integration), `PROD` (production) — set via `COCLI_ENVIRONMENT`
- **1Password integration:** Uses `onepassword-sdk` for credential management; enable with `OP_SERVICE_ACCOUNT_TOKEN` or `OP_ACCOUNT`

## Web Interface (Turboship Status Page)

The project includes a static website (`cocli/web/`) integrated with the CLI:
- Built with Eleventy + Nunjucks templates
- Shared navbar and cookie-based SSO
- Design tokens for consistent theming (light/dark modes)
- Located in `cocli/web/src/` with output in `cocli/web/dist/`

Relevant commands: `cocli render` outputs to the web directory for static deployment.

## Code Standards

- **Imports:** Group stdlib, third-party, local with blank lines
- **Type hints:** Required on all function signatures (mypy strict)
- **Models:** Use Pydantic for validation; place in `cocli/models/`
- **Commands:** Implement in `cocli/commands/` as Typer subcommands
- **Naming:** snake_case for functions/vars, CamelCase for classes/models
- **Docstrings:** Use type hints to document intent; docstrings only if WHY is non-obvious
- **Testing:** BDD style with Gherkin `.feature` files and step definitions; mock external APIs

## Relevant ADRs and Docs

- **ADR-001:** From-Model-to-Model transformation pattern (`docs/adr/from-model-to-model.md`)
- **ADR-002:** Docker worker stability and hot-patching (`docs/adr/docker-worker-stability.md`)
- **Index Intermediates:** Search index creation pattern (`docs/data-management/INDEX-INTERMEDIATES.md`)
- **Test Plan:** Comprehensive testing strategy (`docs/development/test-plan.md`)
- **Architecture:** Application structure and design (`docs/architecture/structure.md`)

See `docs/README.md` for the full documentation index.

## Deployment and Scripts

### Cluster Deployment

Deploy code changes to the Raspberry Pi worker cluster using the registry-based pipeline:

```bash
# Deploy to all nodes (hub + children, staged rollout)
uv run cocli cluster deploy-hotfix --campaign turboship

# Deploy to a specific node
uv run cocli cluster deploy-hotfix --node cocli5x0 --campaign turboship

# Deploy only child nodes (non-hub)
uv run cocli cluster deploy-hotfix --children --campaign turboship
```

**Process:**
1. Syncs code to hub via rsync
2. Hub rebuilds Docker image, verifies it, pushes to registry
3. Child nodes pull the verified image, restart containers
4. Hash-based verification at each stage ensures code is correctly deployed

See `cocli cluster deploy-hotfix --help` for all options.

### Infrastructure

- **Docker:** `Dockerfile` at root; worker images in `docker/rpi-worker/`
- **Scrapers:** Distributed across Raspberry Pi (Google Maps) and AWS Fargate (enrichment)
- **Scripts:** `scripts/` directory includes campaign auditing, cleanup, and import utilities
- **CDK:** AWS infrastructure code in `cdk_scraper_deployment/`

## Contact & Help

For help with Claude Code, use `/help`. For project feedback or bugs, report at https://github.com/anthropics/claude-code/issues.
