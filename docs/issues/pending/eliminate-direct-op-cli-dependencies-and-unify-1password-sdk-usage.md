# Eliminate direct 'op' CLI dependencies and unify 1Password SDK usage

### Overview
The project has partially migrated to the official 1Password Python SDK via `cocli/utils/op_utils.py`. however, numerous direct `subprocess` calls to the `op` CLI remain scattered throughout the scripts, tests, and entrypoints. These direct calls bypass the SDK's benefits (reliability on Windows, Service Account support) and maintain a hard dependency on the CLI's installation and interactive state.

### Problem Statement
Direct `op` CLI usage is fragile and problematic for the following reasons:
1. **Headless Failures**: Direct calls often fail on Raspberry Pi nodes where no interactive terminal is available for `op signin`.
2. **Platform Inconsistency**: Handling `op.exe` (Windows) vs `op` (Linux) manually via subprocess is prone to error.
3. **Identity Fragmentation**: Multiple ways of fetching secrets makes the codebase harder to maintain and audit.

### Proposed Solution
Refactor all remaining instances of `op` CLI usage to use the authoritative `cocli.utils.op_utils.get_op_secret()` function. This function automatically handles the SDK-to-CLI fallback logic and supports the `OP_SERVICE_ACCOUNT_TOKEN` for headless nodes.

### Affected Files to Refactor
- **Python Scripts**: 
    - `import_kml_to_maps.py`: Replace `subprocess.check_output(["op", "read", ...])`.
    - `scripts/create_cognito_user.py`: Replace `subprocess.run(["op", "read", ...])`.
    - `scripts/setup_rpi_wifi.py`: Replace `op whoami` and `op item get`.
    - `cocli/scrapers/event_search_scraper.py`: Update the manual `op signin` prompt logic.
- **Test Suite**:
    - `tests/conftest.py`: Replace direct `op read` calls in test fixtures.
- **Shell/Build**:
    - `cocli/entrypoint.sh`: Refactor to use a small Python helper or ensure it respects the Service Account workflow.
    - `Makefile`: Update `op-check` and `op whoami` targets to be SDK-aware if possible.

### Completion Criteria
1. **CLI Elimination**: A recursive grep for `subprocess` + `op` in `.py` files returns zero results.
2. **Unified Interface**: All secret retrieval flows through `op_utils.py`.
3. **Headless Verification**: The system successfully retrieves secrets when `OP_SERVICE_ACCOUNT_TOKEN` is set, without needing the `op` CLI binary installed or signed in.
4. **Interactive Verification**: Secret retrieval still triggers Hello/Biometrics on local machines via the SDK/CLI fallback.
5. **Stability**: `make test` and `make lint` pass with 100% success.
