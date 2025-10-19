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
	source $(VENV_DIR)/bin/activate && uv pip install -e . && playwright install

test: install ## Run tests using pytest
	source $(VENV_DIR)/bin/activate && pytest -s tests/

lint: install ## Run mypy to perform static type checking
	source $(VENV_DIR)/bin/activate && mypy --config-file pyproject.toml .

test-file: install ## Run a specific test file, e.g., make test-file FILE=tests/test_google_maps_scraper.py
	source $(VENV_DIR)/bin/activate && pytest $(FILE)

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
render-kml: install ## Render KML for the current campaign context
	$(VENV_DIR)/bin/cocli render kml

.PHONY: scrape-prospects
scrape-prospects: install ## Scrape prospects for the current campaign context
	$(VENV_DIR)/bin/cocli campaign scrape-prospects

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
import-prospects: install ## Import prospects from the current campaign
	$(VENV_DIR)/bin/cocli google-maps-cache to-company-files

.PHONY: import-customers
import-customers: install ## Import customers from the turboship campaign
	$(VENV_DIR)/bin/cocli import-customers /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customers.csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customer_addresses.csv --tag customer --tag turboship

.PHONY: render-prospects-kml
render-prospects-kml: install ## Render KML for turboship prospects
	$(VENV_DIR)/bin/cocli render-prospects-kml turboship

.PHONY: populate-email-providers
populate-email-providers: install ## Populate the cache with common email providers
	$(VENV_DIR)/bin/cocli flag-email-providers gmail.com yahoo.com hotmail.com outlook.com aol.com icloud.com live.com msn.com yandex.ru mail.ru

.PHONY: ingest-prospects
ingest-prospects: install ## Ingest the existing prospects.csv file for the current campaign into the cache
	$(VENV_DIR)/bin/cocli google-maps-csv to-google-maps-cache

.PHONY: ingest-existing-customers
ingest-existing-customers: install ## Ingest the existing customers.csv file into the cache
	$(VENV_DIR)/bin/cocli ingest-google-maps-csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customers.csv

.PHONY: prospects-with-emails
prospects-with-emails:
	rg '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' \
		cocli_data/scraped_data/turboship/prospects/prospects.csv >> \
		cocli_data/scraped_data/turboship/prospects/prospects_with_emails.csv

.PHONY: debug-google-maps-scraper
debug-google-maps-scraper: install ## Run the Google Maps scraper in headed mode with debug tools for debugging
	source $(VENV_DIR)/bin/activate && pytest tests/debug_google_maps_scraper.py

.PHONY: docker-build
docker-build: ## Build the docker image
	@docker build -t enrichment-service .

.PHONY: docker-run-enrichment

docker-run-enrichment: ## Start docker enrichment service

	@docker run -d -p 8000:8000 --name cocli-enrichment enrichment-service



.PHONY: migrate-website-cache

migrate-website-cache: install ## Migrate website cache to the new index

	$(VENV_DIR)/bin/python scripts/migrate_website_cache.py
