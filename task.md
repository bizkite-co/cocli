# Task: UI/Service Layer Decoupling

## Objective
Formalize the interface between the CLI/TUI and the core business logic by centralizing operations in `CampaignService`. This ensures that both UIs behave identically and that business rules (like updating `.envrc` on campaign switch) are not duplicated.

## Phase 1: CampaignService Consolidation (Active)
- [ ] **Extract Context Logic**: Move the AWS Profile and `.envrc` update logic from `cocli/commands/campaign/mgmt.py:set_default_campaign` into a new `CampaignService.activate_campaign()` method.
- [ ] **Unified Config Access**: Add a `get_config()` and `update_config()` method to `CampaignService` that handles Pydantic validation and TOML serialization.
- [ ] **TUI Refactor**: Update `cocli/tui/campaign_app.py` to use `CampaignService` for saving edits instead of `_save_campaign` (direct TOML write).

## Phase 2: Search Service Integration
- [ ] **Standardize Search**: Ensure `cocli/application/search_service.py` is the sole provider for the TUI's "Fuzzy Search" and the CLI's `fz` command.

## Phase 3: Worker Service Extraction
- [ ] **Move Orchestration**: Create `cocli/application/worker_service.py` and move the async loops from `cocli/commands/worker.py`.

## Verification
- [ ] `make test` passes.
- [ ] `cocli campaign set <name>` correctly updates `.envrc`.
- [ ] Editing a campaign in `cocli campaign edit` (TUI mode) persists changes correctly via the service.
