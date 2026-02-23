# Auth Provider Plugin Architecture (2026-02-21)

## Context
Current authentication (AWS credentials, Google Maps passwords) is tightly coupled to 1Password and specifically uses a bridge to `op.exe` for Windows Hello/biometric support in WSL. This has proven fragile (e.g., `accept4 failed 110` vsock errors) and limits environment flexibility.

**GitHub Issue:** [bizkite-co/cocli#2](https://github.com/bizkite-co/cocli/issues/2)

## Requirements
1.  **Pluggable Backends:** Move away from hardcoded `op` or `op.exe` calls. Define an `AuthProvider` protocol.
2.  **Supported Providers:**
    *   1Password (via CLI and new 1Password SDK).
    *   Standard Environment Variables (Direct fallback).
    *   Keychain/Secret Service (Linux/macOS standard).
    *   Open Source alternatives (e.g., Bitwarden, KeepassXC).
3.  **Discovery:** The system should auto-detect available providers or allow campaign-level configuration (e.g., `auth_provider = "1password-sdk"`).

## Immediate Issues
*   `op.exe` bridge in WSL is currently failing with vsock timeouts.
*   Biometric prompts are not triggering, blocking S3 operations.

## Roadmap
- [ ] Implement `cocli.core.auth` module with base `AuthProvider` class.
- [ ] Migrate `1password-aws-credentials.sh` logic into a Python-native provider.
- [ ] Integrate with the 1Password SDK for more robust cross-platform connectivity.
