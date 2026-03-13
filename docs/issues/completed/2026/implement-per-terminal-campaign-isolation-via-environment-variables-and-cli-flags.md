# Implement per-terminal campaign isolation via environment variables and CLI flags

### Overview
The current system relies on a global `default_campaign` stored in the `cocli_config.toml`. While this works for single-task workflows, it prevents a user from running different campaigns in parallel across multiple terminal sessions (e.g., `roadmap` in one tab, `fullertonian` in another) without constantly overwriting the global state.

### Problem Statement
The "Global Default" pattern creates several friction points:
1. **Race Conditions**: Switching campaigns in one terminal changes the context for all subsequent commands in other terminals.
2. **Workflow Rigidity**: Users cannot easily monitor or supervise two different campaigns simultaneously on the same machine.
3. **Configuration Drift**: It's easy to forget which campaign is "active" globally, leading to data being added to the wrong directory (though datagram routing helped mitigate this for gossip, local CLI commands still suffer).

### Proposed Solution: Per-Terminal Context
Implement a hierarchical campaign resolution strategy that allows for transient, session-specific overrides.

1. **Hierarchy of Truth**:
   - **CLI Flag**: `cocli --campaign roadmap <command>` (Highest priority)
   - **Environment Variable**: `export COCLI_CAMPAIGN=roadmap` (Session-level priority)
   - **Global Config**: `cocli_config.toml` (Fallback/Default)

2. **Technical Implementation**:
   - Update `cocli/core/config.py:get_campaign()` to check `os.environ.get("COCLI_CAMPAIGN")` before reading the TOML file.
   - Add a global `--campaign` (alias `-c`) option to the main `typer.Typer` app in `cocli/main.py`. 
   - Ensure the `main_callback` injects this flag into the environment or a shared context state.
   - Refactor the TUI to prominently display the "Active Context" and ensure all internal service calls respect the transient campaign.

### Completion Criteria
1. **Parallel Execution**: Demonstrate running `cocli tui` for `roadmap` in Terminal A and `cocli tui` for `fullertonian` in Terminal B simultaneously, with both reflecting their respective data.
2. **Environment Priority**: Verify that `COCLI_CAMPAIGN=x` correctly overrides the value in `cocli_config.toml`.
3. **CLI Consistency**: All commands (e.g., `cocli add`, `cocli audit`, `cocli sync`) correctly target the specified campaign when passed the `-c` flag.
4. **Gossip Integrity**: Ensure that gossip datagrams generated from a transiently-specified campaign are correctly tagged with that campaign name.
5. **No Regression**: Standard `cocli` commands still work using the global default if no override is provided.

---
**Completed in commit:** `2a1b302`
