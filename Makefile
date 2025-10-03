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

.PHONY: import-turboship
import-turboship: install ## Import turboship customers
	$(VENV_DIR)/bin/cocli import-turboship /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customers.csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customer_addresses.csv

.PHONY: render-kml
render-kml: install ## Render KML for turboship campaign
	$(VENV_DIR)/bin/cocli render kml turboship

.PHONY: scrape-prospects
scrape-prospects: install ## Scrape prospects for turboship campaign
	$(VENV_DIR)/bin/cocli campaign scrape-prospects turboship

.PHONY: deduplicate-prospects
deduplicate-prospects: install ## Deduplicate prospects for turboship campaign
	$(VENV_DIR)/bin/cocli deduplicate prospects turboship

.PHONY: enrich-prospects
enrich-prospects: install ## Enrich prospects for turboship campaign
	$(VENV_DIR)/bin/cocli enrich-websites cocli_data/scraped_data/turboship/prospects/prospects.csv

.PHONY: enrich-customers
enrich-customers: install ## Enrich customers for turboship campaign with Google Maps data
	$(VENV_DIR)/bin/cocli enrich-customers turboship

.PHONY: prospects-with-emails
prospects-with-emails:
	rg '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' \
		cocli_data/scraped_data/turboship/prospects/prospects.csv >> \
		cocli_data/scraped_data/turboship/prospects/prospects_with_emails.csv