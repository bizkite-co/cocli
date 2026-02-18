# Docker Deployment Strategy (Raspberry Pi Cluster)

This document outlines the "Expert" strategy for deploying the `cocli` worker cluster. 

## 1. The Core Philosophy: Sync & Build
Instead of trying to "patch" running containers (which leads to dependency drift and instability), we treat the cluster as a fleet of **immutable workers**.

1.  **Sync**: The entire local repository is synchronized to the RPi node via `rsync`.
2.  **Build**: A local `docker build` is executed *on the RPi*.
3.  **Atomic Swap**: The old container is stopped and a new one is started using the fresh image.

### Why Build on the RPi?
*   **Architecture Parity**: Ensures the ARM64 binaries are correctly compiled.
*   **Dependency Integrity**: `uv pip install` inside the Dockerfile ensures that `pyproject.toml` is the absolute source of truth. No "ghost" modules.
*   **Layer Caching**: Docker caches layers. If only your code changed (and not `pyproject.toml`), the heavy dependency installation step is skipped, making the "build" take only seconds.

## 2. Optimization: Code Signatures
We use `scripts/check_code_signature.py` to generate an MD5 hash of all source files. 

### The "Is It Hot?" Check
To make the hotfix truly "hot," the deployment script performs the following check on the RPi:
1.  Generate the current code signature.
2.  Compare it against the signature of the last successful build.
3.  **Skip Build**: If the signatures match, we skip the `docker build` entirely and just restart the container if needed.

## 3. Campaign Switching
The Docker image is **Code-Specific**, not **Campaign-Specific**.

*   If you switch from `roadmap` to `turboship` but **make no code changes**, you do **not** need to rebuild the image.
*   The `CAMPAIGN_NAME` is passed as an environment variable at runtime (`docker run -e CAMPAIGN_NAME=...`).
*   The supervisor will automatically pick up the new campaign context from the environment.

## 4. Troubleshooting
If a deployment fails:
1.  **Check Logs**: `make log-rpi-all`
2.  **Prune Docker**: `make clean-docker-pi` (removes old layers and build cache).
3.  **Force Build**: Run the deploy script with a clean slate to ensure no cached layers are causing issues.
