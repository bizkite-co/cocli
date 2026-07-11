# Command Disposition Matrix

> Load-bearing review artifact for the CLI Consolidation Epic.
> Per-command record of which intermediates must survive consolidation and where.
> This file is seeded by Phase 1 (orphan deletion) and comprehensively filled by Phase 0.

## Deleted orphaned command modules (Phase 1, 2026-07-11)

The following files in `cocli/commands/` were never registered in
`commands/__init__.py` or `main.py` and had no live Python imports. They were
removed in a single deletion PR.

| File | Disposition | Notes |
|------|-------------|-------|
| `scrape.py` | Deleted | 1-line deprecation stub; replaced by `cocli campaign achieve-goal`. No logic. |
| `lead_scrape.py` | Deleted | 1-line deprecation stub; replaced by `cocli campaign achieve-goal`. No logic. |
| `enrich_websites.py` | Deleted | 1-line stub ("temporarily removed pending shared-browser refactor"). No logic. |
| `google_maps.py` | Deleted | 3-line empty Typer app; deprecated, replaced by `cocli campaign achieve-goal`. No logic. |
| `import_turboship.py` | Deleted, logic noted below | Superseded by `import-customers` (`commands/import_customers.py`). Unique ShopifyData enrichment logic extracted to this note. |

### import_turboship.py — ShopifyData enrichment (preserved logic)

`import_turboship.py` was the older Turboship CSV importer. Its core flow
(merge customers + addresses CSVs, derive company from email domain, create
Person/Company files) has been superseded by `commands/import_customers.py`,
which uses newer domain models (`CompanyName`, `CompanyAddress`, `PhoneNumber`,
`EmailAddress`, `WebsiteDomainCsv`/`WebsiteDomainCsvManager` for email-provider
detection instead of the hardcoded `COMMON_DOMAINS` list).

**Logic NOT present in `import_customers.py`** (must be re-integrated if
Shopify enrichment is still desired):

- Writes a `ShopifyData` (`cocli/models/shopify.py`) enrichment record to
  `person_dir/enrichments/shopify.md` as YAML frontmatter for each imported
  customer (lines 115-138 of the deleted file).
- `ShopifyData` captures: id, first_name, last_name, email, phone, tags,
  company_name, address, city, state, zip, country, address_phone.

**Disposition:** Reintegration should be a concern of the application-API
extraction phase (Phase 4) or the import-cluster merge (Phase 5), not a
command-module concern. If Shopify enrichment is still required, add it to
`import_customers.py` (or its extracted service) as an opt-in flag rather
than a separate command.

## `no_args_is_help` enforcement (2026-07-11)

Per the policy (Mark, 2026-07-10), all commands executed without parameters
should trigger the `--help` output. This pass added `no_args_is_help=True` to:

- Every `typer.Typer(...)` **group app** that was missing it (`query`, `sync`,
  `smart-sync`, `render`, `exclude`, `deduplicate`, `infrastructure`, `index`,
  `campaign events`, the `data queue` and `audit queue` sub-apps).
- Every **leaf command** re-registered via `app.command(name=...)(func)` in
  `cocli/commands/__init__.py` that has a required positional argument or a
  required option — the flag is set on the registration call itself because
  Tyrus/Click does not survive the per-decorator flag through the
  re-registration (`main.command(name=...)(func)` discards the decorator-side
  `no_args_is_help` metadata).
- Every **sub-app command** with required Arguments/Options — the flag is set
  on the `@app.command(...)` decorator, which DOES survive `app.add_typer`
  (the per-app `registered_commands` list is copied intact).

Behavior verified by walking the actual CLI tree on bare invocation: every
path that takes a required argument now shows full help (Arguments + Options
panels) rather than a terse "Missing argument/option" error.

### Documented zero-arg action-command exceptions

These continue to RUN (exit 0) on bare invocation rather than show help, by
design — they take no required parameters and legitimately act with defaults:

- `cocli` (root group — callback prints env-info banner then dispatches).
- `cocli status` (`commands/status.py`) — `@app.callback(invoke_without_command=True)`;
  shows environment/campaign metrics with no params.
- `cocli init` (`commands/init.py`) — bootstraps the cocli config file.
- `cocli next`, `cocli recent` (`commands/meetings.py`) — interactive list of
  upcoming/recent meetings.
- `cocli fz` (`commands/fz.py`) — interactive fuzzy finder over companies.
- `cocli tui` (`commands/tui.py`) — launches the Textual TUI full-screen app.
- `cocli compile-enrichment` (`commands/compile_enrichment.py`) — runs with
  current campaign context (`Optional[str]` argument default `None`).
- `cocli enrich-shopify-data`, `cocli scrape-shopify-myip`,
  `cocli process-shopify-scrapes` — configured entirely via options with
  sensible defaults; bare invocation runs the workflow with defaults.
- All `audit` commands whose only arguments are optional (e.g.
  `cocli audit fs`, `cocli audit cli`, `cocli audit cluster`,
  `cocli audit gm-list-html`, `cocli audit schemas`, `cocli audit tui`).
- All `index` commands except `write-datapackage` (the only one taking a
  required `index` argument) — `compact`, `status`, `backfill-domains` run
  with sensible defaults.
- `cocli sync pi-results`, `cocli sync indexes` — optional args with defaults.
- `cocli cluster status` / `top` / `gossip-audit` / `sync-clocks` /
  `prune` — read-only or zero-arg cluster actions.
- `cocli data list` — lists known datapackages, no params required.
- All `task` commands except `create` (e.g. `task list`, `task next`,
  `task tree`, `task sync`, `task start`, `task done`, `task prioritize`).
- All `dev` commands (validation/pipeline helpers with optional args).
- All `video` commands except `add`, `create-thumbnail`, `extract-screenshots`
  (the three with required `video` / `video_slug` arguments).
- All `prospects` commands (`to-hubspot-csv`, `enrich-from-queue`,
  `tag-from-csv`) take only optional args.
- All `companies` commands (`list-recent`).
- All `worker` commands (`start`, `gm-list`, `gm-details`, etc.) — start
  supervisor loops with config-driven defaults.