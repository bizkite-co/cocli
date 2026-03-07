# Screaming Architecture Implementation Output

## Overview
We are implementing a "Universal Structure Dump" capability across the `cocli` ecosystem. This allows the application to self-report its internal organization across multiple domains (TUI, CLI, Filesystem, and eventually API/Services).

## Principles
- **Domain Autonomy:** Each domain (e.g., the TUI) is responsible for reporting its own structure.
- **Interoperability:** Output formats should be simple and informative to support heterogeneous processing.
- **Longevity:** Avoid esoteric constraints; prefer text-based, human-readable DSLs.
- **Alignment:** The output should directly map to the "Screaming Architecture" folder structures (e.g., `docs/tui/screen/`).

## Implementation Status

### TUI Domain
- **Mechanism:** `cocli tui --dump-tree [PATH]`
- **DSL:** Indented text tree representing the Textual widget hierarchy.
- **Logic:** "Smart Condensing" in `cocli/tui/utils.py` summarizes repetitive items (like ListItems) while preserving unique structural components (widgets with IDs).
- **Trigger:** Integrated into `Makefile` via `make tui-tree`.

### CLI Domain (Planned)
- **Mechanism:** `cocli audit --cli`
- **DSL:** Indented tree of Typer commands, subcommands, and options.
- **Goal:** Align CLI command hierarchy with the modular logic in `cocli/commands/`.

### Filesystem Domain (Planned)
- **Mechanism:** `cocli audit --fs`
- **DSL:** Indented tree of the `data/` and `docs/` hierarchies, highlighting "Screaming Architecture" compliance.

### Boundary Definitions (Guidance)
As we separate Scraper Workers from CRM UI, we will need to identify "Domain Boundaries" in the reports:
- **Metadata Tags:** Append tags like `[CRM]`, `[WORKER]`, or `[SHARED]` to nodes in the tree.
- **Dependency Mapping:** Link widgets or commands to the specific `ServiceContainer` attributes they rely on.
- **Visual Separation:** Group components in the report by their deployment target (e.g., "Fargate-Ready" vs. "Residential-Only").

## Future Tasks
- [ ] Implement CLI structure dumper.
- [ ] Implement Filesystem structure auditor.
- [ ] Add runtime TUI "Structure Save" hotkey (e.g., `ctrl+s` in dev mode).
- [ ] Implement `make task` for enhanced Markdown-based task management.
