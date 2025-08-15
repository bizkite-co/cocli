# Current Task: Get the `import` command to work

This task focuses on getting the `cocli import` command fully functional within the Python application.

## Sub-tasks:

1.  **Verify `uv` virtual environment setup**: Ensure a virtual environment is created and active.
    *   Command: `uv venv`
2.  **Install `cocli` in editable mode**: Install the current Python project in editable mode to allow direct execution from source.
    *   Command: `uv pip install -e .`
3.  **Identify Python `import` command implementation**: Locate the Python code responsible for handling the `import` command as defined in `cocli/main.py` (based on `pyproject.toml`).
4.  **Examine existing bash `import` logic**: Review the `bin/cocli` script and the `lib/importers/` directory to understand how the bash version of the `import` command works and what importers it supports (e.g., `lead-sniper`).
5.  **Compare bash and Python `import` functionality**: Determine what functionality from the bash `import` command needs to be migrated or verified in the Python implementation.
6.  **Test Python `import` command**: Attempt to run the Python `import` command with a sample file (if available or easily creatable) and observe its behavior.
7.  **Debug and Refine**: Address any errors or unexpected behavior encountered during testing.