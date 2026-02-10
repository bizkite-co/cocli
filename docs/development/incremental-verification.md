# Incremental Verification

To maintain a high-speed development cycle without sacrificing data integrity, `cocli` uses a "Code Signature" system to skip redundant linting and testing.

## Overview
The verification process (ruff, mypy, pytest) is the most time-consuming part of the "Fast Path" deployment. By hashing the source code and comparing it to a "Last Known Good" signature, we can instantly bypass these steps when no changes are detected.

## The Code Signature
The signature is an MD5 hash of all core source files, including:
- `cocli/` (Core logic and models)
- `scripts/` (Maintenance and recovery)
- `tests/` and `features/` (Verification suite)
- `Makefile` and `pyproject.toml` (Build configuration)

**Excluded**: `data/`, `.git/`, `__pycache__`, and `.venv`.

## Implementation
- **Script**: `scripts/check_code_signature.py`
- **Storage**: `.code_signature.md5` (Root directory, git-ignored)

### Makefile Integration
The `lint` and `test` targets use the `--check` flag to determine if execution is necessary:

```makefile
lint:
    @if python3 scripts/check_code_signature.py --check; then \
        echo "Code signature matches. Skipping lint."; \
    else \
        # ... run lint ...
        python3 scripts/check_code_signature.py --update; \
    fi
```

## Workflow
1. **Developer makes a change**: The signature no longer matches.
2. **Developer runs `make lint`**: The system detects the change, runs the full check, and updates the signature on success.
3. **Developer runs `make test`**: The system sees the updated signature from the previous step and **skips** the tests (assuming they already passed during the last full run).
4. **Fast Deployment**: The `fast-deploy-cluster` command can run instantly knowing the local state is already validated.
