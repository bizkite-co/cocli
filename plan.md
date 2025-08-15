# Plan for `cocli` PyPi Deployment

This document outlines the detailed plan to get the `cocli` Python application installable locally and then set up a GitHub Actions workflow for PyPi deployment, ensuring it's easily installable for others.

## Phase 1: Local Installation and Verification

The `pyproject.toml` indicates that `cocli` is a Python package with an entry point. We'll leverage `uv` for this.

1.  **Create a `uv` virtual environment**: This isolates project dependencies.
    *   Command: `uv venv`
2.  **Install `cocli` in editable mode**: This allows you to run the package directly from its source code, making development easier.
    *   Command: `uv pip install -e .`
3.  **Verify local execution**: After installation, the `cocli` command should be available within the virtual environment.
    *   Command: `uv run cocli --help`
4.  **Address the `bin/cocli` bash script**: The `docs/chats/20250813-150830-session-summary.md` mentions a "final, robust wrapper script at `~/.local/bin/cocli` that uses `uv run` to correctly execute the Python application from its virtual environment." The `bin/cocli` file in your repository is a bash script that seems to dispatch to other bash scripts in `lib/`. This suggests a hybrid or incomplete transition. For a clean PyPi deployment, the Python package should be the primary entry point.
    *   **Action**: I will propose removing the `bin/cocli` bash script and the `lib/` directory (which contains old bash scripts like `add`, `find`, `importers/lead-sniper`) if they are no longer needed, and rely solely on the Python entry point defined in `pyproject.toml`. If these bash scripts still contain functionality not yet migrated to Python, we'll need to discuss that.

## Phase 2: PyPi Deployment Workflow

Once local installation is confirmed, we'll set up the automated deployment.

1.  **Understand PyPi Deployment Requirements**:
    *   PyPi requires a `PYPI_API_TOKEN` for authentication. This token should be stored securely as a GitHub Secret.
    *   The package needs to be built into distribution archives (source distribution `.tar.gz` and wheel distribution `.whl`).
    *   These archives are then uploaded to PyPi.
2.  **Create GitHub Actions Workflow File**: We'll create a new file at `.github/workflows/pypi_publish.yml`.
    *   **Trigger**: The workflow will be triggered on `release` creation (e.g., when you publish a new release on GitHub).
    *   **Environment Setup**:
        *   Checkout the repository.
        *   Set up Python.
        *   Install `uv`.
    *   **Build Package**: Use `uv build` to create the necessary distribution files.
    *   **Publish to PyPi**: Use `uv publish` (or `twine upload` if `uv publish` isn't directly suitable for CI/CD in this context, though `uv` is generally preferred). This step will use the `PYPI_API_TOKEN` from GitHub Secrets.
3.  **Secure PyPi API Token**: I will provide instructions on how to create a PyPi API token and add it as a repository secret in GitHub.
4.  **Testing the Workflow**: I will outline how to test the workflow by creating a draft release or a tag.

```mermaid
graph TD
    A[Start] --> B{Phase 1: Local Installation & Verification};

    B --> B1[Create uv virtual environment];
    B1 --> B2[Install cocli in editable mode: uv pip install -e .];
    B2 --> B3[Verify local execution: uv run cocli --help];
    B3 --> B4{Confirm if bin/cocli bash script and lib/ are still needed};
    B4 -- Yes, functionality not migrated --> B5[Discuss migration strategy or alternative handling];
    B4 -- No, fully migrated --> B6[Remove bin/cocli and lib/ directories];
    B6 --> C[Phase 2: PyPi Deployment Workflow];

    C --> C1[Understand PyPi deployment requirements];
    C1 --> C2[Create GitHub Actions workflow file: .github/workflows/pypi_publish.yml];
    C2 --> C3[Define workflow steps: Trigger, Setup, Build, Publish];
    C3 --> C4[Explain GitHub Secrets for PyPi API token];
    C4 --> C5[Outline workflow testing];
    C5 --> D[End];