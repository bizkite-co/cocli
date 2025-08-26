SHELL := /bin/bash

.PHONY: test install clean list-packages

# Define the virtual environment directory
VENV_DIR := ./.venv

# Install development dependencies using uv
install:
	uv sync --extra dev
	source $(VENV_DIR)/bin/activate && uv pip install -e .

# Run tests using pytest
test: install
	source $(VENV_DIR)/bin/activate && pytest tests/

# Run tests using pytest
activate: install
	source $(VENV_DIR)/bin/activate

# List installed packages
list-packages: install
	source $(VENV_DIR)/bin/activate && uv pip list

# Clean up virtual environment and uv.lock
clean:
	rm -rf $(VENV_DIR) uv.lock
