# cocli/web

Static dashboard shell for `cocli web deploy`. Built with Eleventy
(`.eleventy.js`), pages are Nunjucks/Markdown under this directory, output
goes to `build/web` and is synced to S3 + fronted by CloudFront.

## Pages and components

Each page pulls in only the `_includes/components/*.njk` it needs -
`dashboard.js`'s functions are shared across pages but **not every function
assumes every element exists**. If you add a DOM lookup to `dashboard.js`,
guard it (`if (el) {...}`) rather than assuming the component that defines
it is on every page. `index.md` (main dashboard) and `config.md` (config
editor) currently include different, non-overlapping sets of components -
e.g. `report_table.njk` / `worker_stats.njk` are only on `config.md`, not
`index.md`. A previous bug had `renderReport()`'s report-table code and its
unrelated download-link code in one function guarded by a single
`if (!document.getElementById('report-body')) return;` - on `index.md`,
where that element doesn't exist, the guard skipped the download-link logic
too. Keep functions single-purpose, or scope early-return guards to just
the DOM section they're actually guarding.

Third-party JS/CSS should be vendored as same-origin static files (see
`papaparse.min.js`) rather than loaded from a CDN `<script src>`/`<link>` -
cross-origin CDN resources are subject to browser tracking-prevention
blocking, which silently breaks the page with no visible error.

## Auth

Login is Cognito Hosted UI (implicit grant), driven by `checkAuth()` in
`_includes/layout.njk` and completed by `auth-callback.md`. The values it
needs (`userPoolId`, `userPoolClientId`, `userPoolDomain`, ...) are injected
at build time into `window.COCLI_CONFIG` by `_data/campaign.js`, which reads
them from environment variables set in `cocli/commands/web.py`'s deploy
command, falling back to the campaign's own `config.toml`.

**Important**: cocli does not own the Cognito User Pool / Client for every
campaign. For `turboship`, auth infra is defined and deployed by a separate
repo, `turboheatweldingtools/homepage` (`lib/turboship-auth-stack.ts`),
which can recreate its User Pool Client under a new ID independently of
this repo - that happened once already and silently broke login (the client
ID baked into `config.toml` pointed at a client that no longer existed;
Cognito returned `invalid_request` and `checkAuth()` had no visible failure
mode for it).

To avoid hardcoding that repo's naming scheme into cocli, a campaign can
opt into a live SSM lookup at deploy time by setting these keys under
`[aws]` in its `config.toml`:

```toml
[aws]
cognito_client_id_ssm_param = "/prod/cocli/cognito/client-id"
cognito_domain_ssm_param = "/prod/cocli/cognito/domain-url"
```

`WebService.fetch_cdk_outputs()` (`cocli/application/web_service.py`) reads
these two keys generically - no campaign name ever appears in that code.
If set, it overrides the static `cocli_user_pool_client_id` /
`cocli_user_pool_domain` config values with whatever the external stack
currently publishes at those SSM paths. Campaigns that don't set them (e.g.
`roadmap`, which has its own separate web deploy target) just use their
static config values untouched - each campaign's web publish target is
independent; nothing here assumes `turboship`'s specific infrastructure.

## Testing

`tests/e2e/test_dashboard_downloads.py` logs into the live dashboard with
1Password-sourced test credentials and asserts the download links actually
populate and trigger a file download - run via `make test-e2e`.
