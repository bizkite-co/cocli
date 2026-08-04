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
- All `video` commands except `add` / `import`, `create-thumbnail`,
  `extract-screenshots` (required `video` / `video_slug` arguments).
- All `prospects` commands (`to-hubspot-csv`, `enrich-from-queue`,
  `tag-from-csv`) take only optional args.
- All `companies` commands (`list-recent`).
- All `worker` commands (`start`, `gm-list`, `gm-details`, etc.) — start
  supervisor loops with config-driven defaults.

---

## Duplicate registration and `name=""` flattening flags

### Duplicate `exclude` registration

`exclude` is registered at **two levels**:

1. **Root level:** `cocli/commands/__init__.py:71` — `app.add_typer(exclude.app, name="exclude")`
   → `cocli exclude add/remove/list`
2. **Campaign level:** `cocli/commands/campaign/__init__.py:26` — `app.add_typer(exclude.app, name="exclude")`
   → `cocli campaign exclude add/remove/list`

Both point to the same `cocli/commands/exclude.py` module. The root-level
registration is a convenience alias; the campaign-level registration is the
canonical location (exclusions are per-campaign). **Recommendation:** Keep
campaign-level as canonical; deprecate root-level alias with a re-export
shim in Phase 3.

### `name=""` flattening in `campaign/__init__.py`

Seven sub-apps are registered with `name=""` in `cocli/commands/campaign/__init__.py:13-19`:

```python
app.add_typer(mgmt.app, name="", ...)        # → campaign status, set, show, etc.
app.add_typer(workflow.app, name="", ...)     # → campaign start-workflow, next-step
app.add_typer(planning.app, name="", ...)     # → campaign import-contacts, generate-grid, etc.
app.add_typer(viz.app, name="", ...)          # → campaign visualize-coverage, publish-kml, etc.
app.add_typer(prospecting.app, name="", ...)  # → campaign prepare-mission, achieve-goal, etc.
app.add_typer(enrichment.app, name="", ...)   # → campaign queue-enrichment
app.add_typer(curation.app, name="", ...)     # → campaign curate-events
```

This flattens the intermediate sub-app namespaces so their commands appear
as top-level `cocli campaign <command>`. This is intentional and correct —
the sub-app files are organizational (one file per concern) but the user
surface should be flat under `campaign`.

---

## Full command disposition matrix

Every registered command from `docs/cli/actual_tree.txt` (115 commands)
plus the 5 orphaned modules (deleted in Phase 1).

**Column legend:**
- **Disposition:** `keep` = stays as-is; `move` = relocate to new path; `merge-into-X` = consolidate into command X; `drop` = remove; `deprecate-alias` = keep as hidden alias with warning
- **Target location:** Provisional future path (finalized in Phase 2)
- **Biz-logic:** `app-api` = already extracted to `cocli/application/` or `cocli/services/`; `embedded` = logic lives in command module (Phase 4/5 extraction candidate)
- **Intermediates:** Files/queues/indexes/S3 paths the command writes that must survive
- **Automation callers:** External invocations (subprocess, TUI, Makefile, scripts, Docker, VSCode)
- **Usage evidence:** Where the command appears in docs/README/TUI

### Root-level commands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli add` | `commands/add.py:16` | keep | `cocli add` | embedded | company files, indexes | — | README, CLAUDE.md |
| `cocli add-email` | `commands/add_email.py:13` | keep | `cocli add-email` | embedded | company files, campaign index | — | — |
| `cocli add-meeting` | `commands/add_meeting.py:81` | keep | `cocli add-meeting` | embedded | meetings files | — | — |
| `cocli context` | `commands/context.py:9` | keep | `cocli context` | embedded | context state file | — | — |
| `cocli enrich-customers` | `commands/enrich_customers.py:15` | keep | `cocli enrich-customers` | embedded | company enrichments | — | — |
| `cocli enrich-shopify-data` | `commands/enrich_shopify_data.py:16` | keep | `cocli enrich-shopify-data` | embedded | company enrichments | launch.json:154 | — |
| `cocli compile-enrichment` | `commands/compile_enrichment.py:11` | keep | `cocli compile-enrichment` | embedded | company `_index.md` files | — | — |
| `cocli flag-email-providers` | `commands/flag_email_providers.py:9` | keep | `cocli flag-email-providers` | embedded | website cache | — | — |
| `cocli fz` | `commands/fz.py:41` | keep | `cocli fz` | embedded | — | run_fz.py:8, launch.json:103 | README |
| `cocli google-maps-cache-to-company-files` | `commands/import_companies.py:148` | move → `cocli data import google-maps-cache` | `cocli data import google-maps-cache` | embedded | company files, enrichments | — | — |
| `cocli google-maps-csv-to-google-maps-cache` | `commands/ingest_google_maps_csv.py:15` | move → `cocli data import google-maps-csv` | `cocli data import google-maps-csv` | embedded | google maps cache | — | — |
| `cocli import-customers` | `commands/import_customers.py:22` | move → `cocli data import customers` | `cocli data import customers` | embedded | company files, person files | — | CLAUDE.md |
| `cocli import-data` | `commands/import_data.py:13` | move → `cocli data import` | `cocli data import` | embedded | varies by importer | launch.json:114 | CLAUDE.md |
| `cocli init` | `commands/init.py:3` | keep | `cocli init` | embedded | config file | Makefile:14 | README |
| `cocli next` | `commands/meetings.py:126` | keep | `cocli next` | embedded | — | — | — |
| `cocli open-company-folder` | `commands/view.py:661` | keep | `cocli open-company-folder` | embedded | — | — | — |
| `cocli process-shopify-scrapes` | `commands/process_shopify_scrapes.py:9` | keep | `cocli process-shopify-scrapes` | embedded | shopify index | — | — |
| `cocli recent` | `commands/meetings.py:187` | keep | `cocli recent` | embedded | — | — | — |
| `cocli render-prospects-kml` | `commands/render_prospects_kml.py:12` | merge-into `cocli render kml` | `cocli render kml` | embedded | KML exports | — | — |
| `cocli scrape-shopify-myip` | `commands/scrape_shopify.py:10` | keep | `cocli scrape-shopify-myip` | embedded | google maps cache | launch.json:140 | — |
| `cocli status` | `commands/status.py:14` | keep | `cocli status` | app-api (`reporting_service`) | — | — | README, CLAUDE.md |
| `cocli view-company` | `commands/view.py:52` | keep | `cocli view-company` | embedded | — | — | — |
| `cocli view-meetings` | `commands/view.py:628` | keep | `cocli view-meetings` | embedded | — | — | — |

### `admin` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli admin archive-campaign` | `commands/admin.py:13` | keep | `cocli admin archive-campaign` | embedded | S3 archive | — | — |
| `cocli admin refresh-dev` | `commands/admin.py:59` | keep | `cocli admin refresh-dev` | app-api (`deployment`) | DEV data dir | — | — |

### `audit` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli audit cli` | `commands/audit.py:92` | keep | `cocli audit cli` | embedded | — | — | CLAUDE.md, test_cli_surface.py |
| `cocli audit cluster` | `commands/audit.py:670` | keep | `cocli audit cluster` | embedded | — | — | CLAUDE.md |
| `cocli audit enrichment` | `commands/audit.py:1041` | keep | `cocli audit enrichment` | embedded | enrichment metrics | — | — |
| `cocli audit fs` | `commands/audit.py:122` | keep | `cocli audit fs` | embedded | audit report | — | CLAUDE.md |
| `cocli audit gm-list-html` | `commands/audit.py:1330` | keep | `cocli audit gm-list-html` | embedded | audit log | queues_view.py:311 | — |
| `cocli audit rollout` | `commands/audit.py:190` | keep | `cocli audit rollout` | embedded | rollout diagnostics | — | — |
| `cocli audit schemas` | `commands/audit.py:1175` | keep | `cocli audit schemas` | embedded | schema validation | — | — |
| `cocli audit scrape` | `commands/audit.py:331` | keep | `cocli audit scrape` | embedded | scrape audit report | — | — |
| `cocli audit tui` | `commands/audit.py:544` | keep | `cocli audit tui` | embedded | — | — | — |
| `cocli audit queue` | `commands/audit.py:17` | keep (group) | `cocli audit queue` | — | — | — | — |
| `cocli audit queue export-cases` | `commands/audit.py:1813` | keep | `cocli audit queue export-cases` | embedded | test case USVs | — | — |
| `cocli audit queue gm-list` | `commands/audit.py:43` | keep | `cocli audit queue gm-list` | embedded | audit log, reviewed USVs | — | — |
| `cocli audit queue purge-leases` | `commands/audit.py:2001` | keep | `cocli audit queue purge-leases` | embedded | lease cleanup | — | — |
| `cocli audit queue replay` | `commands/audit.py:1690` | keep | `cocli audit queue replay` | embedded | corrected USVs | — | — |
| `cocli audit queue tile-status` | `commands/audit.py:1909` | keep | `cocli audit queue tile-status` | embedded | — | — | — |
| `cocli audit queue validate` | `commands/audit.py:1354` | keep | `cocli audit queue validate` | embedded | reviewed USVs | — | — |

### `campaign` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli campaign achieve-goal` | `campaign/prospecting.py:1128` | keep | `cocli campaign achieve-goal` | embedded | mission, frontier, queues | launch.json:32 | — |
| `cocli campaign add` | `campaign/mgmt.py:103` | keep | `cocli campaign add` | embedded | campaign config | — | — |
| `cocli campaign add-location` | `campaign/mgmt.py:274` | keep | `cocli campaign add-location` | embedded | campaign config | — | — |
| `cocli campaign add-query` | `campaign/mgmt.py:220` | keep | `cocli campaign add-query` | embedded | campaign config | — | — |
| `cocli campaign audit` | `campaign/audit.py:116` | keep (group) | `cocli campaign audit` | — | — | — | — |
| `cocli campaign audit companies` | `campaign/audit.py:206` | keep | `cocli campaign audit companies` | embedded | — | — | — |
| `cocli campaign audit company` | `campaign/audit.py:253` | keep | `cocli campaign audit company` | embedded | — | — | — |
| `cocli campaign audit locations` | `campaign/audit.py:116` | keep | `cocli campaign audit locations` | embedded | — | — | — |
| `cocli campaign audit summary` | `campaign/audit.py:297` | keep | `cocli campaign audit summary` | embedded | — | — | — |
| `cocli campaign audit tiles` | `campaign/audit.py:149` | keep | `cocli campaign audit tiles` | embedded | — | — | — |
| `cocli campaign bucket` | `campaign/mgmt.py:360` | keep | `cocli campaign bucket` | embedded | — | — | — |
| `cocli campaign build-mission-index` | `campaign/prospecting.py:753` | keep | `cocli campaign build-mission-index` | embedded | mission, frontier | — | — |
| `cocli campaign compile-lifecycle` | `campaign/mgmt.py:416` | keep | `cocli campaign compile-lifecycle` | app-api (`lifecycle_manager`) | lifecycle index | — | — |
| `cocli campaign compile-to-call` | `campaign/mgmt.py:601` | keep | `cocli campaign compile-to-call` | embedded | to-call list | — | — |
| `cocli campaign coverage-gap` | `campaign/planning.py:208` | keep | `cocli campaign coverage-gap` | embedded | coverage report | — | — |
| `cocli campaign create-batch` | `campaign/prospecting.py:631` | keep | `cocli campaign create-batch` | embedded | batch USV, mission_state.toml | — | — |
| `cocli campaign curate-events` | `campaign/curation.py:64` | keep | `cocli campaign curate-events` | embedded | event data | — | — |
| `cocli campaign discover-venues` | `campaign/prospecting.py:1041` | keep | `cocli campaign discover-venues` | embedded | venue data | — | — |
| `cocli campaign edit` | `campaign/mgmt.py:29` | keep | `cocli campaign edit` | embedded | campaign config | — | — |
| `cocli campaign events` | `campaign/events.py:9` | keep (group) | `cocli campaign events` | — | — | — | — |
| `cocli campaign events generate-tasks` | `campaign/events.py:9` | keep | `cocli campaign events generate-tasks` | embedded | event scrape tasks | — | — |
| `cocli campaign exclude` | `commands/exclude.py:14` | keep (group, canonical) | `cocli campaign exclude` | — | exclusion index | — | — |
| `cocli campaign exclude add` | `commands/exclude.py:14` | keep | `cocli campaign exclude add` | embedded | exclusion index | — | — |
| `cocli campaign exclude list` | `commands/exclude.py:49` | keep | `cocli campaign exclude list` | embedded | — | — | — |
| `cocli campaign exclude remove` | `commands/exclude.py:34` | keep | `cocli campaign exclude remove` | embedded | exclusion index | — | — |
| `cocli campaign export-resources` | `campaign/viz.py:340` | keep | `cocli campaign export-resources` | embedded | resources.json | — | — |
| `cocli campaign generate-grid` | `campaign/planning.py:103` | keep | `cocli campaign generate-grid` | embedded | grid USVs | Makefile:658 | — |
| `cocli campaign geocode-locations` | `campaign/mgmt.py:328` | keep | `cocli campaign geocode-locations` | embedded | campaign config | — | — |
| `cocli campaign import-contacts` | `campaign/planning.py:23` | keep | `cocli campaign import-contacts` | embedded | company files | — | — |
| `cocli campaign import-prospects` | `campaign/planning.py:70` | keep | `cocli campaign import-prospects` | embedded | company files | — | — |
| `cocli campaign monitor-batch` | `campaign/prospecting.py:876` | keep | `cocli campaign monitor-batch` | embedded | — | — | — |
| `cocli campaign next-step` | `campaign/workflow.py:31` | keep | `cocli campaign next-step` | embedded | — | — | — |
| `cocli campaign path-check` | `campaign/mgmt.py:657` | keep | `cocli campaign path-check` | embedded | — | — | — |
| `cocli campaign prepare-mission` | `campaign/prospecting.py:532` | keep | `cocli campaign prepare-mission` | embedded | mission, frontier, tiles | — | — |
| `cocli campaign prospects` | `commands/prospects.py:51` | keep (group) | `cocli campaign prospects` | — | — | — | — |
| `cocli campaign prospects enrich-from-queue` | `commands/prospects.py:152` | keep | `cocli campaign prospects enrich-from-queue` | embedded | enrichment queue | launch.json:70 | — |
| `cocli campaign prospects tag-from-csv` | `commands/prospects.py:457` | keep | `cocli campaign prospects tag-from-csv` | embedded | — | — | — |
| `cocli campaign prospects to-hubspot-csv` | `commands/prospects.py:51` | keep | `cocli campaign prospects to-hubspot-csv` | embedded | HubSpot CSV | launch.json:57 | — |
| `cocli campaign publish-kml` | `campaign/viz.py:201` | keep | `cocli campaign publish-kml` | embedded | S3 KML uploads | — | — |
| `cocli campaign queue-batch` | `campaign/prospecting.py:421` | keep | `cocli campaign queue-batch` | embedded | queue USVs | — | — |
| `cocli campaign queue-enrichment` | `campaign/enrichment.py:16` | keep | `cocli campaign queue-enrichment` | embedded | enrichment queue | — | — |
| `cocli campaign queue-mission` | `campaign/prospecting.py:830` | keep | `cocli campaign queue-mission` | embedded | queue USVs | — | — |
| `cocli campaign queue-scrapes` | `campaign/prospecting.py:286` | keep | `cocli campaign queue-scrapes` | embedded | queue USVs | — | — |
| `cocli campaign remove-location` | `campaign/mgmt.py:301` | keep | `cocli campaign remove-location` | embedded | campaign config | — | — |
| `cocli campaign remove-query` | `campaign/mgmt.py:247` | keep | `cocli campaign remove-query` | embedded | campaign config | — | — |
| `cocli campaign restore-names` | `campaign/mgmt.py:479` | keep | `cocli campaign restore-names` | embedded | company files | — | — |
| `cocli campaign rollout` | `campaign/rollout.py:98` | keep (group) | `cocli campaign rollout` | — | — | — | — |
| `cocli campaign rollout audit` | `campaign/rollout.py:302` | keep | `cocli campaign rollout audit` | embedded | — | — | — |
| `cocli campaign rollout broadcast-config` | `campaign/rollout.py:147` | keep | `cocli campaign rollout broadcast-config` | embedded | S3 config | — | — |
| `cocli campaign rollout progress` | `campaign/rollout.py:378` | keep | `cocli campaign rollout progress` | embedded | — | — | — |
| `cocli campaign rollout pull-config` | `campaign/rollout.py:236` | keep | `cocli campaign rollout pull-config` | embedded | local config | — | — |
| `cocli campaign rollout push` | `campaign/rollout.py:279` | keep | `cocli campaign rollout push` | embedded | S3 tasks, batches | — | — |
| `cocli campaign rollout push-config` | `campaign/rollout.py:201` | keep | `cocli campaign rollout push-config` | embedded | S3 config | — | — |
| `cocli campaign rollout report` | `campaign/rollout.py:518` | keep | `cocli campaign rollout report` | embedded | — | — | — |
| `cocli campaign rollout run` | `campaign/rollout.py:98` | keep | `cocli campaign rollout run` | embedded | rollout state | — | — |
| `cocli campaign rollout status` | `campaign/rollout.py:324` | keep | `cocli campaign rollout status` | embedded | — | — | — |
| `cocli campaign rollout sync` | `campaign/rollout.py:430` | keep | `cocli campaign rollout sync` | embedded | S3 sync | — | — |
| `cocli campaign sanitize-discovery` | `campaign/mgmt.py:552` | keep | `cocli campaign sanitize-discovery` | embedded | mission, frontier, queues | — | — |
| `cocli campaign list` | `campaign/mgmt.py` | keep | `cocli campaign list` | embedded | — | — | — |
| `cocli campaign set` | `campaign/mgmt.py:123` | keep | `cocli campaign set` | embedded | context state | — | README |
| `cocli campaign show` | `campaign/mgmt.py:155` | keep | `cocli campaign show` | embedded | — | — | — |
| `cocli campaign start-workflow` | `campaign/workflow.py:10` | keep | `cocli campaign start-workflow` | embedded | — | — | — |
| `cocli campaign status` | `campaign/mgmt.py:194` | keep | `cocli campaign status` | embedded | — | — | — |
| `cocli campaign unset` | `campaign/mgmt.py:146` | keep | `cocli campaign unset` | embedded | context state | — | — |
| `cocli campaign upload-kml-coverage` | `campaign/viz.py:307` | deprecate-alias | `cocli campaign upload-kml-coverage` | embedded | S3 KML | — | — |
| `cocli campaign visualize-coverage` | `campaign/viz.py:21` | keep | `cocli campaign visualize-coverage` | embedded | KML exports | — | — |
| `cocli campaign visualize-legacy-scrapes` | `campaign/viz.py:164` | keep | `cocli campaign visualize-legacy-scrapes` | embedded | KML exports | — | — |

### `cluster` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli cluster deploy-hotfix` | `commands/cluster.py:16` | keep | `cocli cluster deploy-hotfix` | app-api (`deployment`, `cluster_service`) | Docker images | cluster_view.py:41 | CLAUDE.md |
| `cocli cluster gossip-audit` | `commands/cluster.py:45` | keep | `cocli cluster gossip-audit` | embedded | — | — | — |
| `cocli cluster prune` | `commands/cluster.py:208` | keep | `cocli cluster prune` | embedded | — | — | — |
| `cocli cluster status` | `commands/cluster.py:175` | keep | `cocli cluster status` | embedded | — | — | — |
| `cocli cluster stop` | `commands/cluster.py:146` | keep | `cocli cluster stop` | embedded | — | cluster_view.py:51 | — |
| `cocli cluster sync-clocks` | `commands/cluster.py:105` | keep | `cocli cluster sync-clocks` | embedded | — | — | — |
| `cocli cluster top` | `commands/cluster.py:61` | keep | `cocli cluster top` | embedded | — | — | — |

### `companies` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli companies list-recent` | `commands/companies.py:9` | keep | `cocli companies list-recent` | embedded | — | — | — |

### `data` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli data describe` | `commands/data.py:87` | keep | `cocli data describe` | embedded | — | — | — |
| `cocli data inspect` | `commands/data.py:461` | keep | `cocli data inspect` | embedded | — | — | — |
| `cocli data list` | `commands/data.py:61` | keep | `cocli data list` | embedded | — | — | — |
| `cocli data locate` | `commands/data.py:148` | keep | `cocli data locate` | embedded | — | — | — |
| `cocli data metrics` | `commands/data.py:214` | keep | `cocli data metrics` | embedded | — | — | — |
| `cocli data queue` | `commands/data.py:27` | keep (group) | `cocli data queue` | — | — | — | — |
| `cocli data queue compact` | `commands/data.py:519` | keep | `cocli data queue compact` | embedded | compacted USVs | — | — |
| `cocli data sample` | `commands/data.py:160` | keep | `cocli data sample` | embedded | — | — | — |
| `cocli data search` | `commands/data.py:387` | keep | `cocli data search` | embedded | — | — | — |

### `deduplicate` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli deduplicate deduplicate` | `commands/deduplicate.py:12` | keep | `cocli deduplicate deduplicate` | embedded | deduplicated company files | — | — |

### `dev` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli dev move-map-tiles-to-processing` | `commands/dev.py:265` | keep | `cocli dev move-map-tiles-to-processing` | embedded | map-tile queue state | — | — |
| `cocli dev process-map-tile` | `commands/dev.py:359` | keep | `cocli dev process-map-tile` | embedded | gm-list queue | — | — |
| `cocli dev run-discovery-gen-stages` | `commands/dev.py:138` | keep | `cocli dev run-discovery-gen-stages` | embedded | mission, frontier, tiles | — | — |
| `cocli dev run-discovery-pipeline` | `commands/dev.py:49` | keep | `cocli dev run-discovery-pipeline` | embedded | full pipeline artifacts | — | — |

### `enrich` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli enrich contacts` | `commands/enrich.py:117` | keep | `cocli enrich contacts` | embedded | contact enrichments | — | — |
| `cocli enrich list` | `commands/enrich.py:96` | keep | `cocli enrich list` | embedded | — | — | — |
| `cocli enrich run` | `commands/enrich.py:19` | keep | `cocli enrich run` | embedded | company enrichments | — | — |

### `exclude` subcommands (root-level alias)

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli exclude` | `commands/exclude.py:14` | deprecate-alias → `cocli campaign exclude` | `cocli campaign exclude` | embedded | exclusion index | — | — |
| `cocli exclude add` | `commands/exclude.py:14` | deprecate-alias → `cocli campaign exclude add` | `cocli campaign exclude add` | embedded | exclusion index | — | — |
| `cocli exclude list` | `commands/exclude.py:49` | deprecate-alias → `cocli campaign exclude list` | `cocli campaign exclude list` | embedded | — | — | — |
| `cocli exclude remove` | `commands/exclude.py:34` | deprecate-alias → `cocli campaign exclude remove` | `cocli campaign exclude remove` | embedded | exclusion index | — | — |

### `index` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli index backfill-domains` | `commands/index.py:201` | keep | `cocli index backfill-domains` | embedded | domain index shards | — | — |
| `cocli index compact` | `commands/index.py:34` | keep | `cocli index compact` | app-api (`compact`) | WAL, checkpoint, S3 | — | — |
| `cocli index status` | `commands/index.py:143` | keep | `cocli index status` | embedded | — | — | — |
| `cocli index write-datapackage` | `commands/index.py:244` | keep | `cocli index write-datapackage` | embedded | datapackage.json | — | — |

### `infrastructure` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli infrastructure deploy-infra` | `commands/infrastructure.py:52` | keep | `cocli infrastructure deploy-infra` | app-api (`deployment_service`) | CDK stack | deployment_service.py:18 | — |
| `cocli infrastructure start-worker` | `commands/infrastructure.py:18` | keep | `cocli infrastructure start-worker` | embedded | SSH, Docker | — | — |
| `cocli infrastructure stop-workers` | `commands/infrastructure.py:10` | keep | `cocli infrastructure stop-workers` | embedded | SSH, Docker | — | — |

### `query` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli query query-prospects-location` | `commands/query.py:112` | keep | `cocli query query-prospects-location` | embedded | prospects CSV | — | — |

### `render` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli render kml` | `commands/render.py:10` | keep | `cocli render kml` | embedded | KML exports | — | — |
| `cocli render kml-coverage` | `commands/render.py:23` | merge-into `cocli render kml` | `cocli render kml` | embedded | KML exports | — | — |

### `smart-sync` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli smart-sync active-leases` | `commands/smart_sync.py:352` | keep | `cocli smart-sync active-leases` | embedded | S3 sync | — | — |
| `cocli smart-sync all` | `commands/smart_sync.py:451` | keep | `cocli smart-sync all` | embedded | S3 sync | — | — |
| `cocli smart-sync campaign-config` | `commands/smart_sync.py:431` | keep | `cocli smart-sync campaign-config` | embedded | S3 sync | — | — |
| `cocli smart-sync companies` | `commands/smart_sync.py:241` | keep | `cocli smart-sync companies` | embedded | S3 sync | — | — |
| `cocli smart-sync emails` | `commands/smart_sync.py:277` | keep | `cocli smart-sync emails` | embedded | S3 sync | — | — |
| `cocli smart-sync enrichment-queue` | `commands/smart_sync.py:330` | keep | `cocli smart-sync enrichment-queue` | embedded | S3 sync | — | — |
| `cocli smart-sync prospects` | `commands/smart_sync.py:258` | keep | `cocli smart-sync prospects` | embedded | S3 sync | — | — |
| `cocli smart-sync queues` | `commands/smart_sync.py:401` | keep | `cocli smart-sync queues` | embedded | S3 sync | — | — |
| `cocli smart-sync raw` | `commands/smart_sync.py:374` | keep | `cocli smart-sync raw` | embedded | S3 sync | — | — |
| `cocli smart-sync scraped-areas` | `commands/smart_sync.py:296` | keep | `cocli smart-sync scraped-areas` | embedded | S3 sync | — | — |
| `cocli smart-sync scraped-tiles` | `commands/smart_sync.py:313` | keep | `cocli smart-sync scraped-tiles` | embedded | S3 sync | — | — |

### `sync` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli sync config` | `commands/sync.py:92` | keep | `cocli sync config` | app-api (`sync_service`) | S3 config | — | — |
| `cocli sync indexes` | `commands/sync.py:56` | keep | `cocli sync indexes` | app-api (`sync_service`) | S3 indexes | — | — |
| `cocli sync pi-results` | `commands/sync.py:123` | keep | `cocli sync pi-results` | app-api (`sync_service`) | S3 results | — | — |
| `cocli sync queue` | `commands/sync.py:10` | keep | `cocli sync queue` | app-api (`sync_service`) | S3 queue | — | — |

### `task` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli task create` | `commands/task.py:247` | keep | `cocli task create` | embedded | task files | — | — |
| `cocli task done` | `commands/task.py:177` | keep | `cocli task done` | embedded | task files, git commit | — | — |
| `cocli task list` | `commands/task.py:49` | keep | `cocli task list` | embedded | — | — | — |
| `cocli task next` | `commands/task.py:86` | keep | `cocli task next` | embedded | — | — | — |
| `cocli task prioritize` | `commands/task.py:100` | keep | `cocli task prioritize` | embedded | task files | — | — |
| `cocli task start` | `commands/task.py:129` | keep | `cocli task start` | embedded | task files | — | — |
| `cocli task sync` | `commands/task.py:42` | keep | `cocli task sync` | embedded | task index | — | — |
| `cocli task tree` | `commands/task.py:109` | keep | `cocli task tree` | embedded | — | — | — |

### `video` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli video add` | `commands/video.py` | keep | `cocli video add` | embedded | video queue | — | — |
| `cocli video import` | `commands/video.py` | keep | `cocli video import` (alias of `add`) | embedded | video queue | — | — |
| `cocli video auth` | `commands/video.py:607` | keep | `cocli video auth` | app-api (`youtube`) | OAuth tokens | — | — |
| `cocli video create-thumbnail` | `commands/video.py:344` | keep | `cocli video create-thumbnail` | embedded | thumbnail image | — | — |
| `cocli video extract-screenshots` | `commands/video.py:377` | keep | `cocli video extract-screenshots` | embedded | screenshot images | — | — |
| `cocli video normalize` | `commands/video.py:129` | keep | `cocli video normalize` | embedded | normalized video queue | — | — |
| `cocli video package` | `commands/video.py:228` | keep | `cocli video package` | embedded | packaged video queue | — | — |
| `cocli video upload` | `commands/video.py:418` | keep | `cocli video upload` | app-api (`youtube`) | YouTube video | — | — |

### `view` subcommands (leaf commands)

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli open-company-folder` | `commands/view.py:661` | keep | `cocli open-company-folder` | embedded | — | — | — |
| `cocli view-company` | `commands/view.py:52` | keep | `cocli view-company` | embedded | — | — | — |
| `cocli view-meetings` | `commands/view.py:628` | keep | `cocli view-meetings` | embedded | — | — | — |

### `web` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli web deploy` | `commands/web.py:17` | keep | `cocli web deploy` | embedded | S3 web shell, KMLs | scripts/update_campaign_infra_config.py:105 | — |
| `cocli web report` | `commands/web.py:236` | keep | `cocli web report` | embedded | JSON report | — | — |

### `worker` subcommands

| Command path | Source | Disposition | Target location | Biz-logic | Intermediates | Automation callers | Usage evidence |
|---|---|---|---|---|---|---|---|
| `cocli worker enrichment` | `commands/worker.py:139` | keep | `cocli worker enrichment` | embedded | enrichment queue | — | — |
| `cocli worker gm-details` | `commands/worker.py:108` | keep | `cocli worker gm-details` | embedded | gm-details queue | — | — |
| `cocli worker gm-list` | `commands/worker.py:76` | keep | `cocli worker gm-list` | embedded | gm-list queue | — | — |
| `cocli worker gossip` | `commands/worker.py:238` | keep | `cocli worker gossip` | embedded | WAL journals | — | — |
| `cocli worker orchestrate` | `commands/worker.py:170` | keep | `cocli worker orchestrate` | app-api (`worker_service`) | S3 heartbeats | cluster_service.py:237, deployment.py:405, Dockerfile:54 | CLAUDE.md |
| `cocli worker supervisor` | `commands/worker.py:49` | keep | `cocli worker supervisor` | app-api (`worker_service`) | S3 heartbeats | — | — |

---

## Per-cluster recommendations

Six overlap clusters identified in the CLI Consolidation Epic. These are
provisional recommendations for Phase 2 review.

### 1. Sync cluster

**Commands:** `cocli sync config/indexes/pi-results/queue`, `cocli smart-sync all/companies/prospects/emails/...`, `cocli campaign rollout sync`

**Current state:** Three sync surfaces with significant overlap:
- `cocli sync` — low-level per-queue/config sync via `sync_service.py`
- `cocli smart-sync` — higher-level compound sync (calls `sync_service` internally)
- `cocli campaign rollout sync` — rollout-specific sync (calls `sync_service` internally)

**Recommendation:** Consolidate into `cocli sync` as the canonical entry point.
- `cocli sync all` replaces `cocli smart-sync all`
- `cocli sync companies/prospects/emails/...` replaces `cocli smart-sync` subcommands
- `cocli campaign rollout sync` becomes an internal call to `cocli sync rollout`
- `cocli smart-sync` kept as deprecated aliases during transition

**Artifacts to preserve:** S3 queue sync, S3 indexes, S3 config, S3 scraped areas.

### 2. Audit cluster

**Commands:** `cocli audit cli/fs/cluster/enrichment/schemas/scrape/rollout/tui/gm-list-html`, `cocli audit queue gm-list/validate/replay/export-cases/tile-status/purge-leases`, `cocli campaign audit locations/tiles/companies/company/summary`

**Current state:** Two audit surfaces:
- `cocli audit` — system-wide auditing (filesystem, schemas, scrape workflow, cluster)
- `cocli campaign audit` — campaign-specific audit (locations, tiles, companies)

**Recommendation:** Keep both but clarify scope:
- `cocli audit` = system/infrastructure auditing (fs, schemas, cluster, scrape workflow)
- `cocli campaign audit` = campaign data auditing (locations, tiles, companies)
- No merge needed; the split is intentional and clear

**Artifacts to preserve:** Audit logs, reviewed USVs, corrected USVs, test case USVs.

### 3. Enrichment cluster

**Commands:** `cocli enrich run/list/contacts`, `cocli enrich-customers`, `cocli enrich-shopify-data`, `cocli compile-enrichment`, `cocli campaign queue-enrichment`, `cocli campaign prospects enrich-from-queue`, `cocli worker enrichment`

**Current state:** Enrichment is scattered across 7 command paths:
- `cocli enrich` — generic enrichment runner
- `cocli enrich-customers` — Google Maps enrichment for customers
- `cocli enrich-shopify-data` — Shopify domain enrichment
- `cocli compile-enrichment` — compile enrichment into `_index.md`
- `cocli campaign queue-enrichment` — enqueue companies for enrichment
- `cocli campaign prospects enrich-from-queue` — consume enrichment queue
- `cocli worker enrichment` — worker that processes enrichment tasks

**Recommendation:** Consolidate into `cocli enrich`:
- `cocli enrich run/list/contacts` stay as-is
- `cocli enrich customers` replaces `cocli enrich-customers`
- `cocli enrich shopify` replaces `cocli enrich-shopify-data`
- `cocli enrich compile` replaces `cocli compile-enrichment`
- `cocli campaign queue-enrichment` moves to `cocli enrich queue`
- `cocli campaign prospects enrich-from-queue` moves to `cocli enrich consume`
- `cocli worker enrichment` stays (worker entry point, not user-facing)

**Artifacts to preserve:** Enrichment queue, company `_index.md` files, website enrichments.

### 4. Import cluster

**Commands:** `cocli import-data`, `cocli import-customers`, `cocli google-maps-cache-to-company-files`, `cocli google-maps-csv-to-google-maps-cache`, `cocli campaign import-contacts`, `cocli campaign import-prospects`

**Current state:** Six import surfaces with inconsistent naming:
- Root-level imports with verbose names (`google-maps-cache-to-company-files`)
- Campaign-level imports (`import-contacts`, `import-prospects`)
- Generic `import-data` dispatcher

**Recommendation:** Consolidate into `cocli data import`:
- `cocli data import customers` replaces `cocli import-customers`
- `cocli data import google-maps-cache` replaces `cocli google-maps-cache-to-company-files`
- `cocli data import google-maps-csv` replaces `cocli google-maps-csv-to-google-maps-cache`
- `cocli data import-data` → `cocli data import` (dispatcher)
- `cocli campaign import-contacts` stays (campaign-specific)
- `cocli campaign import-prospects` stays (campaign-specific)

**Artifacts to preserve:** Company files, person files, Google Maps cache, enrichment records (ShopifyData).

### 5. Infrastructure cluster

**Commands:** `cocli infrastructure deploy-infra/start-worker/stop-workers`, `cocli cluster deploy-hotfix/status/stop/top/prune/sync-clocks/gossip-audit`

**Current state:** Two infrastructure surfaces:
- `cocli infrastructure` — AWS/CDK deployment, SSH-based worker management
- `cocli cluster` — Raspberry Pi cluster management (Docker, gossip, health)

**Recommendation:** Keep both but clarify scope:
- `cocli infrastructure` = AWS/CDK/cloud infrastructure
- `cocli cluster` = Raspberry Pi/Docker cluster
- No merge needed; the split is intentional (cloud vs. edge)

**Artifacts to preserve:** CDK stacks, Docker images, S3 heartbeats, gossip journals.

### 6. CRM verbs cluster

**Commands:** `cocli add`, `cocli add-email`, `cocli add-meeting`, `cocli view-company`, `cocli view-meetings`, `cocli open-company-folder`, `cocli companies list-recent`, `cocli fz`

**Current state:** CRM-like commands scattered at root level:
- Create: `add`, `add-email`, `add-meeting`
- Read: `view-company`, `view-meetings`, `companies list-recent`, `fz`
- No explicit update/delete commands

**Recommendation:** Consolidate into `cocli crm`:
- `cocli crm add/add-email/add-meeting` (create)
- `cocli crm view-company/view-meetings/list-recent` (read)
- `cocli crm open-company-folder` (action)
- `cocli fz` stays at root (global fuzzy finder, not campaign-scoped)
- Root-level aliases kept during transition

**Artifacts to preserve:** Company files, person files, meetings files, campaign index.
