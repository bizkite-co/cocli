# Task: TUI Parity & Advanced Service Integration

## Objective
Achieve full feature and data parity between the legacy CLI Company View and the new TUI, while continuing to move orchestration logic into the Service Layer.

## Phase 3: TUI/CLI Parity (Active)
### Feature Gaps
- [ ] **Contact Management**: Implement full menu for adding (new/existing), editing, and deleting contacts (currently placeholders).
- [ ] **Add Meeting**: Implement the `a` action for meetings (currently "coming soon").
- [ ] **Meeting Management**: Add ability to open meeting files in the editor (`m`).
- [ ] **Tag Management**: Add `t` and `T` bindings for adding and removing company tags.
- [ ] **Exclude Company**: Implement the `X` binding to add companies to the exclusion list.
- [ ] **Re-enrichment**: Add `r` binding to update domain and trigger re-enrichment.
- [ ] **Enhanced Call**: Update `p` binding to automatically create a meeting entry after the call (CLI parity).
- [ ] **Multi-line Notes**: Add a full-screen `TextArea` editor for the Notes quadrant.

### Data Gaps
- [ ] **Company Markdown**: Display the body text/content of the company's `_index.md`.
- [ ] **Extended Metadata**: Show 'Type', 'Services', 'Products', 'Tech Stack', 'Visits per day', 'Timezone'.
- [ ] **Contact Details**: Show phone numbers in the contacts table.
- [ ] **Meeting Precision**: Show full datetime for meetings instead of just the date.
- [ ] **Note Titles**: Include titles in the notes preview list.

## Phase 4: Person Parity
- [ ] **UI Alignment**: Update Person Detail view to match the 2x2 grid structure.
- [ ] **Inline Edits**: Enable inline editing for all Person fields.

## Phase 5: Service Layer & Worker Extraction
- [ ] **Campaign Consolidation**: Move `.envrc` and AWS Profile logic into `CampaignService.activate_campaign()`.
- [ ] **Worker Orchestration**: Create `cocli/application/worker_service.py` and move async loops from `cocli/commands/worker.py`.

## Verification
- [x] `make test` passes.
- [x] Inline edits for Identity and Address persist correctly.
- [x] Note addition/editing/deletion works with confirmation.
