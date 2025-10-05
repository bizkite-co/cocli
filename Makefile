.PHONY: help
help: ## Display this help screen
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z_-]+:.*?## / {printf "  \033[32m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: init
init: ## Initialize the cocli configuration file
	./.venv/bin/cocli init


# ==============================================================================
# Application Tasks
# ==============================================================================
.PHONY: build
build: install ## Build the application distributables (wheel and sdist)
	@echo "Building the application..."
	uv run python -m build

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

WORKERS ?= 4

.PHONY: enrich-websites
enrich-websites: install ## Enrich all companies with website data
	$(VENV_DIR)/bin/cocli enrich-websites --workers $(WORKERS)

.PHONY: enrich-websites-force
enrich-websites-force: install ## Force enrich all companies with website data
	$(VENV_DIR)/bin/cocli enrich-websites --force --workers $(WORKERS)

.PHONY: enrich-customers
enrich-customers: install ## Enrich customers for turboship campaign with Google Maps data
	$(VENV_DIR)/bin/cocli enrich-customers turboship

.PHONY: import-prospects
import-prospects: install ## Import prospects from the turboship campaign
	$(VENV_DIR)/bin/cocli import-companies /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/prospects/prospects.csv --tag prospect --tag turboship

.PHONY: import-customers
import-customers: install ## Import customers from the turboship campaign
	$(VENV_DIR)/bin/cocli import-customers /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customers.csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customer_addresses.csv --tag customer --tag turboship

.PHONY: render-prospects-kml
render-prospects-kml: install ## Render KML for turboship prospects
	$(VENV_DIR)/bin/cocli render-prospects-kml turboship

.PHONY: populate-email-providers
populate-email-providers: install ## Populate the cache with common email providers
	$(VENV_DIR)/bin/cocli flag-email-providers gmail.com yahoo.com hotmail.com outlook.com aol.com icloud.com live.com msn.com yandex.ru mail.ru

.PHONY: ingest-existing-prospects
ingest-existing-prospects: install ## Ingest the existing prospects.csv file into the cache
	$(VENV_DIR)/bin/cocli ingest-google-maps-csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/prospects/prospects.csv

.PHONY: ingest-existing-customers
ingest-existing-customers: install ## Ingest the existing customers.csv file into the cache
	$(VENV_DIR)/bin/cocli ingest-google-maps-csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customers.csv

.PHONY: prospects-with-emails
prospects-with-emails:
	rg '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' \
		cocli_data/scraped_data/turboship/prospects/prospects.csv >> \
		cocli_data/scraped_data/turboship/prospects/prospects_with_emails.csv