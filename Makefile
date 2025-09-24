.PHONY: help
help: ## Display this help screen
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z_-]+:.*?## / {printf "  \033[32m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ==============================================================================
# Application Tasks
# ==============================================================================
.PHONY: build
build: ## Build the application WAR file

SHELL := /bin/bash

.PHONY: test install clean list-packages

# Define the virtual environment directory
VENV_DIR := ./.venv

open: activate ##Activate the venv and open
	@cocli

install: ## Install development dependencies using uv
	uv sync --extra dev
	source $(VENV_DIR)/bin/activate && uv pip install -e .

test: install ## Run tests using pytest
	source $(VENV_DIR)/bin/activate && pytest tests/

activate: install ## Run tests using pytest
	source $(VENV_DIR)/bin/activate

list-packages: install ## List installed packages
	source $(VENV_DIR)/bin/activate && uv pip list

clean: ## Clean up virtual environment and uv.lock
	rm -rf $(VENV_DIR) uv.lock

.PHONY: install-global
install-global: ## Install the latest version of the app using pipx
	git pull
	pipx install .
