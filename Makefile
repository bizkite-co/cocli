

PHONY: help
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

log: ## Display the last 100 lines of the latest log file
	@latest_log=$$(ls -t .logs/ | head -n 1); \
	echo "Displaying log file: .logs/$$latest_log"; \
	tail -n 100 .logs/$$latest_log

logf: ## Display the last 100 lines of the latest log file
	@latest_log=$$(ls -t .logs/ | head -n 1); \
	echo "Displaying log file: .logs/$$latest_log"; \
	tail -f -n 100 .logs/$$latest_log

logname: ## Get the latest log file name
	@latest_log=$$(ls -t .logs/ | head -n 1); \
	echo ".logs/$$latest_log"

# Note: TUI integration tests are run separately due to terminal driver conflicts.
# Use 'make test-tui-integration' to run them.
test: install ## Run all non-TUI tests using pytest
	-$(MAKE) lint
	source $(VENV_DIR)/bin/activate && pytest -s tests/ --ignore=tests/tui/test_navigation_steps.py

test-unit: install lint ## Run unit tests (excluding TUI folder)
	source $(VENV_DIR)/bin/activate && pytest -s tests/ --ignore=tests/tui

test-tui-integration: install ## Run only the TUI integration tests
	source $(VENV_DIR)/bin/activate && pytest tests/tui/test_navigation_steps.py
	cat .logs/tui.log

report: ## Show the report for the current campaign (Usage: make report [CAMPAIGN=name])
	@$(VENV_DIR)/bin/python scripts/campaign_report.py $(CAMPAIGN)

test-tui: install ## Run TUI test with names
	source $(VENV_DIR)/bin/activate && pytest -v tests/tui

textual: ## Run the app in textual
	@uv tool install textual-dev
	textual run cocli.tui.app

lint: install ## Run ruff and mypy to perform static type checking
	$(VENV_DIR)/bin/ruff check . --fix
	$(VENV_DIR)/bin/python -m mypy --config-file pyproject.toml .

test-file: install ## Run a specific test file, e.g., make test-file FILE=tests/test_google_maps_scraper.py
	source $(VENV_DIR)/bin/activate && pytest $(FILE)

tail-tui: ## Tail the TUI log
	 tail -f ~/.local/share/cocli/logs/tui.log

stable: lint test ## Tag the current commit stable-ground if it suffices
	git tag -d stable-ground && git tag stable-ground

activate: install ## Run tests using pytest
	source $(VENV_DIR)/bin/activate

list-packages: install ## List installed packages
	source $(VENV_DIR)/bin/activate && uv pip list

docker-stop: ## Stop cocli-enrichment
	-@docker rm -f cocli-enrichment

docker-refresh: docker-stop docker-build 
	$(MAKE) start-enricher ## Stop and rebuild docker enrichment

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
deduplicate-prospects: ## Deduplicate prospects CSV (Usage: make deduplicate-prospects [CAMPAIGN=name])
	$(VENV_DIR)/bin/python scripts/deduplicate_prospects.py $(or $(CAMPAIGN), turboship)

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

.PHONY: ingest-prospects
ingest-prospects: install ## Ingest the existing google_maps_prospects.csv file for the current campaign into the cache
	$(VENV_DIR)/bin/cocli google-maps-csv to-google-maps-cache

.PHONY: ingest-existing-customers
ingest-existing-customers: install ## Ingest the existing customers.csv file into the cache
	$(VENV_DIR)/bin/cocli ingest-google-maps-csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customers.csv

.PHONY: queue-scrape-tasks
queue-scrape-tasks: ## Queue scrape tasks for the 'turboship' campaign
	uv run cocli campaign queue-scrapes turboship

.PHONY: prospects-with-emails
prospects-with-emails:
	rg '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' \
		cocli_data/scraped_data/turboship/prospects/google_maps_prospects.csv >> \
		cocli_data/scraped_data/turboship/prospects/prospects_with_emails.csv

.PHONY: debug-google-maps-scraper
debug-google-maps-scraper: install ## Run the Google Maps scraper in headed mode with debug tools for debugging
	source $(VENV_DIR)/bin/activate && pytest tests/debug_google_maps_scraper.py

.PHONY: run-worker-scrape-bg
run-worker-scrape-bg: ## Run the cocli worker scrape command in the background
	@echo "Starting cocli worker scrape in the background using wrapper script..."
	@nohup ./run_worker.sh > worker_scrape.log 2>&1 & \
	echo "cocli worker scrape started in the background. Output redirected to worker_scrape.log"

.PHONY: report-status
report-status: ## Report the status of the SQS queues (ScrapeTasksQueue, EnrichmentQueue)
	@echo "Checking SQS Queue Status..."
	@echo "Scrape Tasks Queue:"
	@aws sqs get-queue-attributes --queue-url "https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-ScrapeTasksQueue9836DB1F-TfprnaM0R5gs" --attribute-names ApproximateNumberOfMessages --profile turboship-support --query 'Attributes.ApproximateNumberOfMessages' --output text
	@echo "Enrichment Queue:"
	@aws sqs get-queue-attributes --queue-url "https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-EnrichmentQueue4D4E619F-srLGUESiUDYU" --attribute-names ApproximateNumberOfMessages --profile turboship-support --query 'Attributes.ApproximateNumberOfMessages' --output text

.PHONY: docker-build
docker-build: ## Build the docker image
	$(eval VERSION := $(shell python3 scripts/increment_version.py))
	@echo "Building version: $(VERSION)"
	@docker buildx build --no-cache --load --build-arg VERSION=$(VERSION) -t enrichment-service .

.PHONY: start-enricher
start-enricher: ## Start docker enrichment service
	@docker run --rm -d -p 8000:8000 --name cocli-enrichment -e LOCAL_DEV=1 -v $(HOME)/.aws:/root/.aws:ro enrichment-service

.PHONY: check-scraper-version
check-scraper-version: ## Check if local website_scraper.py is newer than in the Docker image
	python3 ./scripts/check_scraper_version.py --image-name enrichment-service

.PHONY: deploy-infra
deploy-infra: install ## Deploy AWS Infrastructure (queues, Fargate service definition) using CDK
	@echo "Deploying infrastructure..."
	cd cdk_scraper_deployment && uv run cdk deploy --require-approval never --profile turboship-support

.PHONY: deploy-enrichment
deploy-enrichment: test docker-build ## Build and deploy the enrichment service to AWS Fargate
	@./scripts/deploy_enrichment_service.sh

.PHONY: verify
verify: ## Verify the Fargate deployment
	@./scripts/verify_fargate_deployment.sh

force-update: ## Force Update of service
	aws ecs update-service --cluster ScraperCluster --service EnrichmentService --force-new-deployment --profile turboship-support

.PHONY: ingest-legacy
ingest-legacy: ## Ingest legacy google_maps_prospects.csv into the new queue system (Usage: make ingest-legacy CAMPAIGN=name)
	@if [ -z "$(CAMPAIGN)" ]; then echo "Error: CAMPAIGN variable is required. Usage: make ingest-legacy CAMPAIGN=name"; exit 1; fi
	@$(VENV_DIR)/bin/python scripts/ingest_legacy_csv.py $(CAMPAIGN)

.PHONY: calc-saturation
calc-saturation: ## Calculate saturation scores for target locations (Usage: make calc-saturation [CAMPAIGN=name])
	@$(VENV_DIR)/bin/python scripts/calculate_saturation.py $(or $(CAMPAIGN), turboship)

scrape: calc-saturation ## Run the scraper
	cocli campaign achieve-goal turboship --emails 10000 --cloud-queue --proximity 30\
		$(if $(DEBUG), --debug)\
		$(if $(HEADED), --headed)\
		$(if $(DEBUG), --devtools)\
		$(if $(PANNING_DISTANCE), --panning-distance $(PANNING_DISTANCE))

enrich: ## Run the cloud enricher
	cocli campaign prospects enrich-from-queue turboship --batch-size 6 --cloud-queue

coverage-kml: ## Generate scrape coverage KML
	cocli campaign visualize-coverage turboship

.PHONY: export-emails
export-emails: ## Export enriched emails to CSV (Usage: make export-emails CAMPAIGN=name)
	@if [ -z "$(CAMPAIGN)" ]; then echo "Error: CAMPAIGN variable is required."; exit 1; fi
	@$(VENV_DIR)/bin/python scripts/export_enriched_emails.py $(CAMPAIGN)

.PHONY: queue-missing
queue-missing: ## Identify and queue missing enrichments (Gap Analysis) (Usage: make queue-missing CAMPAIGN=name)
	@if [ -z "$(CAMPAIGN)" ]; then echo "Error: CAMPAIGN variable is required."; exit 1; fi
	@$(VENV_DIR)/bin/python scripts/queue_missing_enrichments.py $(CAMPAIGN)

.PHONY: enrich-domain
enrich-domain: ## Enrich a single domain using the Fargate service (Usage: make enrich-domain DOMAIN=example.com [NAV_TIMEOUT_MS=15000] [FORCE=1] [DEBUG=1])
	@if [ -z "$(DOMAIN)" ]; then echo "Error: DOMAIN is required. Usage: make enrich-domain DOMAIN=example.com"; exit 1; fi
	@echo "Enriching $(DOMAIN)..."
	@python scripts/enrich_domain.py "$(DOMAIN)" \
		$(if $(NAV_TIMEOUT_MS), --navigation-timeout "$(NAV_TIMEOUT_MS)") \
		$(if $(FORCE), --force) \
		$(if $(DEBUG), --debug)

migrate-prospects: ## Migrate google_maps_prospects.csv to file-based index (Usage: make migrate-prospects [CAMPAIGN=name])
	$(VENV_DIR)/bin/python scripts/migrate_prospects_to_index.py $(or $(CAMPAIGN), turboship)

gc-campaigns: ## Commit and push all changes to campaigns and indexes
	cd cocli_data && git add camapaigns indexes && git commit -m "Update campaigns and indexes" && git push;; cd ..

gc-companies: ## Commit and push all changes to companies and people
	cd cocli_data && git add companies people && git commit -m "Update companies and people" && git push;; cd ..