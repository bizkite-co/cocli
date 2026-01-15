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

# Campaign and AWS Profile Resolution
# CAMPAIGN RESOLUTION
# 1. Check if CAMPAIGN was passed in the command line (make CAMPAIGN=xyz)
# 2. Fallback to default campaign in cocli_config.toml
# 3. If neither, set to "ERROR" to trigger checks later.
RAW_CAMPAIGN := $(shell [ -f $(VENV_DIR)/bin/python ] && $(VENV_DIR)/bin/python -c "from cocli.core.config import get_campaign; print(get_campaign() or '')" 2>/dev/null)
CAMPAIGN ?= $(if $(RAW_CAMPAIGN),$(RAW_CAMPAIGN),ERROR)

# Validation function to be called by targets that require a campaign
define validate_campaign
	@if [ "$(CAMPAIGN)" = "ERROR" ]; then \
		echo "ERROR: No campaign specified."; \
		echo "Please either:"; \
		echo "  1. Pass it via CLI: make <target> CAMPAIGN=my-campaign"; \
		echo "  2. Set a default:   cocli campaign set my-campaign"; \
		exit 1; \
	fi
endef

# Dynamically resolve AWS_PROFILE and REGION from campaign config
AWS_PROFILE := $(shell [ -f $(VENV_DIR)/bin/python ] && [ "$(CAMPAIGN)" != "ERROR" ] && $(VENV_DIR)/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('profile', ''))" 2>/dev/null)
REGION := $(shell [ -f $(VENV_DIR)/bin/python ] && [ "$(CAMPAIGN)" != "ERROR" ] && $(VENV_DIR)/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('region', 'us-east-1'))" 2>/dev/null)

open: activate ##Activate the venv and open
	@cocli

op-check: ## Check 1Password auth status
	op whoami

create-cognito-user: op-check ## Create a Cognito user using credentials referenced in campaign config (Usage: make create-cognito-user CAMPAIGN=yyy)
	@if [ "$(CAMPAIGN)" = "ERROR" ]; then echo "Error: CAMPAIGN is required"; exit 1; fi
	./.venv/bin/python scripts/create_cognito_user.py "$(CAMPAIGN)"

install: ## Install development dependencies using uv
	uv sync --extra dev --extra full

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
	$(MAKE) lint
	source $(VENV_DIR)/bin/activate && PYTHONPATH=. pytest -s tests/ --ignore=tests/tui/test_navigation_steps.py --ignore=tests/e2e

test-unit: install lint ## Run unit tests (excluding TUI folder)
	source $(VENV_DIR)/bin/activate && PYTHONPATH=. pytest -s tests/ --ignore=tests/tui

test-tui-integration: install ## Run only the TUI integration tests
	source $(VENV_DIR)/bin/activate && pytest tests/tui/test_navigation_steps.py
	cat .logs/tui.log

report: ## Show the report for the current campaign (Usage: make report [CAMPAIGN=name])
	@PYTHONPATH=. ./.venv/bin/python scripts/campaign_report.py $(CAMPAIGN)

audit-campaign: ## Audit campaign for cross-contamination (Usage: make audit-campaign [CAMPAIGN=name] [FIX=--fix])
	@$(VENV_DIR)/bin/python scripts/audit_campaign_integrity.py $(CAMPAIGN) $(FIX)

coverage-gap: ## Generate a report of unscraped target areas
	@COCLI_DATA_HOME=$(shell pwd)/cocli_data ./.venv/bin/cocli campaign coverage-gap $(CAMPAIGN) --output coverage_gap.csv

test-tui: install lint ## Run TUI test with names
	source $(VENV_DIR)/bin/activate && pytest -v tests/tui

test-e2e: install op-check ## Run end-to-end tests (requires 1Password CLI)
	source $(VENV_DIR)/bin/activate && PYTHONPATH=. pytest tests/e2e

playwright-install: install ## Install Playwright browsers
	source $(VENV_DIR)/bin/activate && playwright install chromium

textual: ## Run the app in textual
	@uv tool install textual-dev
	textual run cocli.tui.app

lint: ## Run ruff and mypy to perform static type checking
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

# Default Data Home (can be overridden by environment variable)
COCLI_DATA_HOME ?= /home/mstouffer/.local/share/cocli_data

.PHONY: import-turboship
import-turboship: install ## Import turboship customers
	$(VENV_DIR)/bin/cocli import-turboship $(COCLI_DATA_HOME)/scraped_data/turboship/customers/customers.csv $(COCLI_DATA_HOME)/scraped_data/turboship/customers/customer_addresses.csv

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
DETAILS_WORKERS ?= 1
SCRAPE_WORKERS ?= 1

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
	$(VENV_DIR)/bin/cocli import-customers $(COCLI_DATA_HOME)/scraped_data/turboship/customers/customers.csv $(COCLI_DATA_HOME)/scraped_data/turboship/customers/customer_addresses.csv --tag customer --tag turboship

.PHONY: render-prospects-kml
render-prospects-kml: install ## Render KML for turboship prospects
	$(VENV_DIR)/bin/cocli render-prospects-kml turboship

.PHONY: publish-kml
publish-kml: ## Generate and upload all KMLs (Coverage, Prospects, Customers) to S3
	@$(VENV_DIR)/bin/cocli campaign publish-kml $(or $(CAMPAIGN), turboship)

.PHONY: publish-config
publish-config: ## Upload the current campaign config.toml to S3
	$(call validate_campaign)
	$(eval BUCKET := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_data_bucket_name', ''))"))
	@if [ -z "$(BUCKET)" ]; then echo "Error: cocli_data_bucket_name not found in config for $(CAMPAIGN)"; exit 1; fi
	aws s3 cp cocli_data/campaigns/$(CAMPAIGN)/config.toml s3://$(BUCKET)/config.toml --profile $(AWS_PROFILE)
	@echo "Config uploaded to s3://$(BUCKET)/config.toml"

.PHONY: ingest-prospects
ingest-prospects: install ## Ingest the existing google_maps_prospects.csv for the current campaign into the cache

.PHONY: ingest-existing-customers
ingest-existing-customers: install ## Ingest the existing customers.csv file into the cache
	$(VENV_DIR)/bin/cocli ingest-google-maps-csv $(COCLI_DATA_HOME)/scraped_data/turboship/customers/customers.csv

.PHONY: queue-scrape-tasks
queue-scrape-tasks: ## Queue scrape tasks for the 'turboship' campaign
	COCLI_DATA_HOME=$(shell pwd)/cocli_data uv run cocli campaign queue-scrapes turboship $(ARGS)

.PHONY: prospects-with-emails
prospects-with-emails:
	rg '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}' \
		cocli_data/scraped_data/turboship/prospects/google_maps_prospects.csv >> \
		cocli_data/scraped_data/turboship/prospects/prospects_with_emails.csv

.PHONY: debug-google-maps-scraper
debug-google-maps-scraper: install ## Run the Google Maps scraper in headed mode with debug tools for debugging
	source $(VENV_DIR)/bin/activate && pytest tests/debug_google_maps_scraper.py

.PHONY: run-worker-gm-list-bg
run-worker-gm-list-bg: ## Run the cocli worker gm-list command in the background
	@echo "Starting cocli worker gm-list in the background using wrapper script..."
	@nohup ./run_worker.sh > worker_scrape.log 2>&1 & \
	echo "cocli worker gm-list started in the background. Output redirected to worker_scrape.log"

.PHONY: watch-report
watch-report: ## Watch the campaign report every 5 seconds
	watch -n 5 -c "make report CAMPAIGN=$(CAMPAIGN)"

.PHONY: docker-build
docker-build: ## Build the docker image
	$(eval VERSION := $(shell python3 scripts/increment_version.py))
	@echo "Building version: $(VERSION)"
	@docker buildx build --no-cache --load --build-arg VERSION=$(VERSION) -t enrichment-service .

.PHONY: docker-verify-local
docker-verify-local: ## Run local Playwright and AWS config sanity checks inside the built Docker image
	@docker run --rm enrichment-service python3 /app/verify_container_sanity.py
	@docker run --rm enrichment-service python3 /app/verify_container_config.py

.PHONY: start-enricher
start-enricher: ## Start docker enrichment service
	@docker run --rm -d -p 8000:8000 --name cocli-enrichment -e LOCAL_DEV=1 -v $(HOME)/.aws:/root/.aws:ro enrichment-service

.PHONY: check-scraper-version
check-scraper-version: ## Check if local website_scraper.py is newer than in the Docker image
	python3 ./scripts/check_scraper_version.py --image-name enrichment-service

.PHONY: deploy-infra
deploy-infra: install ## Deploy AWS Infrastructure (queues, Fargate service definition) using CDK
	$(call validate_campaign)
	@echo "Deploying infrastructure for campaign: $(CAMPAIGN)"
	@echo "Using AWS Profile: $(AWS_PROFILE)"
	@AWS_REGION=$$(./$(VENV_DIR)/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$(CAMPAIGN)'); print(config.get('aws', {}).get('region', 'us-east-1'))"); \
	aws ecr describe-repositories --repository-names cocli-enrichment-service --region $$AWS_REGION --profile $(AWS_PROFILE) > /dev/null 2>&1 || \
	aws ecr create-repository --repository-name cocli-enrichment-service --region $$AWS_REGION --profile $(AWS_PROFILE)
	cd cdk_scraper_deployment && uv venv && . .venv/bin/activate && uv pip install -r requirements.txt && cdk deploy --require-approval never --profile $(AWS_PROFILE) -c campaign=$(CAMPAIGN)
	@$(MAKE) update-infra-config CAMPAIGN=$(CAMPAIGN)

.PHONY: update-infra-config
update-infra-config: install ## Update campaign config.toml with latest SQS URLs from AWS
	$(call validate_campaign)
	PYTHONPATH=. ./$(VENV_DIR)/bin/python scripts/update_campaign_infra_config.py $(CAMPAIGN)

.PHONY: deploy-enrichment
deploy-enrichment: test docker-build ## Build and deploy the enrichment service to AWS Fargate
	@./scripts/deploy_enrichment_service.sh $(CAMPAIGN)

.PHONY: verify
verify: ## Verify the Fargate deployment
	@./scripts/verify_fargate_deployment.sh $(CAMPAIGN)

force-update: ## Force Update of service
	aws ecs update-service --cluster ScraperCluster --service EnrichmentService --force-new-deployment --profile $(AWS_PROFILE) --region $(REGION)

scale: ## Scale the enrichment service (Usage: make scale COUNT=5 [CAMPAIGN=name])
	$(call validate_campaign)
	aws ecs update-service --cluster ScraperCluster --service EnrichmentService --desired-count $(or $(COUNT), 1) --profile $(AWS_PROFILE) --region $(REGION)

.PHONY: ingest-legacy
ingest-legacy: ## Ingest legacy google_maps_prospects.csv into the new queue system (Usage: make ingest-legacy CAMPAIGN=name)
	@if [ -z "$(CAMPAIGN)" ]; then echo "Error: CAMPAIGN variable is required. Usage: make ingest-legacy CAMPAIGN=name"; exit 1; fi
	@$(VENV_DIR)/bin/python scripts/ingest_legacy_csv.py $(CAMPAIGN)

.PHONY: calc-saturation
calc-saturation: ## Calculate saturation scores for target locations (Usage: make calc-saturation [CAMPAIGN=name])
	$(call validate_campaign)
	@$(VENV_DIR)/bin/python scripts/calculate_saturation.py $(CAMPAIGN)

scrape: calc-saturation ## Run the scraper
	$(call validate_campaign)
	cocli campaign achieve-goal $(CAMPAIGN) --emails 10000 --cloud-queue --proximity 30\
		$(if $(DEBUG), --debug)\
		$(if $(HEADED), --headed)\
		$(if $(DEBUG), --devtools)\
		$(if $(PANNING_DISTANCE), --panning-distance $(PANNING_DISTANCE))

enrich: ## Run the cloud enricher
	$(call validate_campaign)
	cocli campaign prospects enrich-from-queue $(CAMPAIGN) --batch-size 6 --cloud-queue

coverage-kml: ## Generate scrape coverage KML
	$(call validate_campaign)
	cocli campaign visualize-coverage $(CAMPAIGN)

.PHONY: analyze-emails
analyze-emails: ## Run deep analysis on emails for the current campaign
	@$(VENV_DIR)/bin/python scripts/debug_stats.py $(CAMPAIGN)

.PHONY: compare-emails
compare-emails: ## Compare current emails to a historical CSV (Usage: make compare-emails FILE=path/to/csv [CAMPAIGN=name])
	$(call validate_campaign)
	@if [ -z "$(FILE)" ]; then echo "Error: FILE is required. Usage: make compare-emails FILE=path/to/csv"; exit 1; fi
	@$(VENV_DIR)/bin/python scripts/compare_missing_emails.py "$(FILE)" --campaign $(CAMPAIGN)

.PHONY: backfill-email-index
backfill-email-index: ## Backfill the email index from existing company files (Usage: make backfill-email-index [CAMPAIGN=name])
	@$(VENV_DIR)/bin/python scripts/backfill_email_index.py $(CAMPAIGN)

.PHONY: recover-prospect-index
recover-prospect-index: ## Reconstruct the prospect index from tagged companies (Usage: make recover-prospect-index [CAMPAIGN=name])
	$(call validate_campaign)
	@$(VENV_DIR)/bin/python scripts/recover_prospect_index.py $(CAMPAIGN)

.PHONY: enrich-place-ids
enrich-place-ids: ## Find missing Place IDs on Google Maps for tagged companies (Usage: make enrich-place-ids [CAMPAIGN=name] [LIMIT=10])
	$(call validate_campaign)
	@$(VENV_DIR)/bin/python scripts/enrich_place_id.py $(CAMPAIGN) --limit $(or $(LIMIT), 0)

.PHONY: rebuild-index
rebuild-index: enrich-place-ids recover-prospect-index ## Full rebuild: Enrich Place IDs then reconstruct the prospect index

.PHONY: sync-scraped-areas
sync-scraped-areas: ## Sync scraped areas from S3
	@$(VENV_DIR)/bin/cocli smart-sync scraped-areas

.PHONY: sync-prospects
sync-prospects: ## Sync prospects from S3
	@$(VENV_DIR)/bin/cocli smart-sync prospects

.PHONY: sync-companies
sync-companies: ## Sync enriched companies from S3
	@$(VENV_DIR)/bin/cocli smart-sync companies

.PHONY: sync-emails
sync-emails: ## Sync email index from S3
	@$(VENV_DIR)/bin/cocli smart-sync emails

.PHONY: sync-enrichment-queue
sync-enrichment-queue: ## Sync enrichment queue from S3
	@$(VENV_DIR)/bin/cocli smart-sync enrichment-queue

.PHONY: sync-queues
sync-queues: ## Sync all local queues from S3
	@$(VENV_DIR)/bin/cocli smart-sync queues

.PHONY: completed-count
completed-count: ## Get the count of completed enrichment tasks on S3
	$(call validate_campaign)
	$(eval BUCKET := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_data_bucket_name', ''))"))
	@echo "Counting completed tasks in s3://$(BUCKET)/campaigns/$(CAMPAIGN)/queues/enrichment/completed/ ..."
	@aws s3 ls s3://$(BUCKET)/campaigns/$(CAMPAIGN)/queues/enrichment/completed/ --recursive --summarize --profile $(AWS_PROFILE) | grep "Total Objects"

.PHONY: recent-completed
recent-completed: ## List the 5 most recently completed enrichment tasks on S3 (efficient pagination)
	$(call validate_campaign)
	$(eval BUCKET := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_data_bucket_name', ''))"))
	@aws s3api list-objects-v2 \
		--bucket $(BUCKET) \
		--prefix campaigns/$(CAMPAIGN)/queues/enrichment/completed/ \
		--max-items 5 \
		--profile $(AWS_PROFILE) \
		--query "sort_by(Contents, &LastModified)[-5:].{Key: Key, LastModified: LastModified}" \
		--output json

.PHONY: push-queue
push-queue: ## Push local queue items to S3 (Usage: make push-queue [CAMPAIGN=name] [QUEUE=enrichment])
	$(call validate_campaign)
	@$(VENV_DIR)/bin/python scripts/push_queue.py --campaign $(CAMPAIGN) --queue $(or $(QUEUE), enrichment)

sync-all: sync-scraped-areas sync-prospects sync-companies sync-emails sync-queues ## Sync all S3 data to local directorys

.PHONY: recent-scrapes
recent-scrapes: sync-scraped-areas ## List the 30 most recent scraped areas (syncs first)
	@find cocli_data/indexes/scraped_areas/ -name "*.json" -printf "%TY-%Tm-%Td %TT %p\n" | sort -r | head -n 30

.PHONY: check-freshness
check-freshness: sync-scraped-areas ## Check if scraped data is fresh (warn if > 4 hours old)
	@latest=$$(find cocli_data/indexes/scraped_areas/ -name "*.json" -printf "%T@ %p\n" | sort -n | tail -1); \
	if [ -z "$$latest" ]; then \
		echo "Warning: No scraped areas found."; \
	else \
		timestamp=$$(echo $$latest | cut -d' ' -f1 | cut -d'.' -f1); \
		filename=$$(echo $$latest | cut -d' ' -f2-); \
		now=$$(date +%s); \
		age=$$((now - timestamp)); \
		hours=$$((age / 3600)); \
		if [ $$age -gt 14400 ]; then \
			printf "\033[0;31m[CRITICAL] Data is stale! Last scrape was %s hours ago.\033[0m\n" "$$hours"; \
			echo "File: $$filename"; \
		else \
			printf "\033[0;32m[OK] Data is fresh. Last scrape was %s hours ago.\033[0m\n" "$$hours"; \
			echo "File: $$filename"; \
		fi \
	fi

.PHONY: export-emails
export-emails: ## Export enriched emails to CSV (Usage: make export-emails [CAMPAIGN=name])
	$(call validate_campaign)
	@PYTHONPATH=. $(VENV_DIR)/bin/python scripts/export_enriched_emails.py $(CAMPAIGN)

.PHONY: queue-missing
queue-missing: ## Identify and queue missing enrichments (Gap Analysis) (Usage: make queue-missing CAMPAIGN=name)
	$(call validate_campaign)
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
	$(call validate_campaign)
	$(VENV_DIR)/bin/python scripts/migrate_prospects_to_index.py $(CAMPAIGN)

gc-campaigns: ## Commit and push all changes to campaigns and indexes
	cd cocli_data && git add camapaigns indexes && git commit -m "Update campaigns and indexes" && git push;; cd ..

gc-companies: ## Commit and push all changes to companies and people
	cd cocli_data && git add companies people && git commit -m "Update companies and people" && git push;; cd ..

.PHONY: deploy-creds-rpi
deploy-creds-rpi: ## Securely deploy AWS credentials to all Raspberry Pis (Usage: make deploy-creds-rpi [CAMPAIGN=name])
	$(call validate_campaign)
	./$(VENV_DIR)/bin/cocli infrastructure deploy-creds --campaign $(CAMPAIGN) --user $(RPI_USER)

# ==============================================================================
# Web Dashboard
# ==============================================================================
.PHONY: web-install
web-install: ## Install web dashboard dependencies
	cd cocli/web && npm install

.PHONY: web-build
web-build: web-install ## Build the web dashboard using 11ty
	$(call validate_campaign)
	cd cocli/web && CAMPAIGN=$(CAMPAIGN) npm run build

.PHONY: web-serve
web-serve: ## Run the web dashboard development server
	cd cocli/web && npm run serve

.PHONY: web-deploy
web-deploy: web-build ## Deploy the web dashboard to S3
	$(call validate_campaign)
	$(eval WEB_BUCKET := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_web_bucket_name', ''))"))
	@if [ -z "$(WEB_BUCKET)" ]; then echo "Error: cocli_web_bucket_name not found in config for $(CAMPAIGN)"; exit 1; fi
	aws s3 sync build/web s3://$(WEB_BUCKET) --profile $(AWS_PROFILE)
	@echo "Dashboard deployed to $(WEB_BUCKET)"

.PHONY: publish-report
publish-report: ## Generate and upload report.json to S3 (Usage: make publish-report [CAMPAIGN=name])
	@PYTHONPATH=. $(VENV_DIR)/bin/python scripts/campaign_report.py $(CAMPAIGN) --upload

.PHONY: compile-companies
compile-companies: install ## Run batch compilation for the current campaign
	$(call validate_campaign)
	$(VENV_DIR)/bin/python scripts/batch_compile_companies.py $(CAMPAIGN)

.PHONY: publish-all
publish-all: sync-companies compile-companies backfill-email-index export-emails publish-report publish-kml web-deploy ## Full sync including compilation and web deployment
	$(call validate_campaign)
	@echo "Full campaign sync completed for $(CAMPAIGN)"

# ==============================================================================
# Planning & Analysis
# ==============================================================================
.PHONY: generate-campaign-grid
generate-campaign-grid: install ## Generate 0.1-degree aligned grid for the current campaign
	COCLI_DATA_HOME=$(shell pwd)/cocli_data uv run cocli campaign generate-grid

.PHONY: hotfix-rpi
hotfix-rpi: ## Push code hotfix to a single RPi (Usage: make hotfix-rpi RPI_HOST=xxx.local)
	@ts=$$(date +%H:%M:%S); echo "[$$ts] Checking connectivity to $(RPI_HOST)..."
	@if ping -c 1 -W 10 $(RPI_HOST) > /dev/null 2>&1; then \
		ts=$$(date +%H:%M:%S); printf "[$$ts] \033[0;32m%s is ONLINE. Pushing hotfix...\033[0m\n" "$(RPI_HOST)"; \
		scp -q -r cocli pyproject.toml $(RPI_USER)@$(RPI_HOST):/tmp/; \
		ssh -o ConnectTimeout=10 $(RPI_USER)@$(RPI_HOST) " \
			for container in \$$(docker ps --filter name=cocli- --format '{{.Names}}'); do \
				echo \"  [\$$(date +%H:%M:%S)] Updating code in \$$container...\"; \
				docker cp /tmp/cocli \$$container:/app/; \
				docker cp /tmp/pyproject.toml \$$container:/app/; \
				echo \"  [\$$(date +%H:%M:%S)] Installing dependencies in \$$container...\"; \
				docker exec \$$container uv pip install psutil --system > /dev/null; \
				docker exec \$$container uv pip install . --system --no-deps > /dev/null; \
				echo \"  [\$$(date +%H:%M:%S)] Restarting \$$container...\"; \
				docker restart \$$container > /dev/null; \
			done \
		"; \
		ts=$$(date +%H:%M:%S); printf "[$$ts] \033[0;32mHotfix applied to %s\033[0m\n" "$(RPI_HOST)"; \
	else \
		ts=$$(date +%H:%M:%S); printf "[$$ts] \033[0;31m%s is OFFLINE or slow (10s timeout). Skipping.\033[0m\n" "$(RPI_HOST)"; \
	fi

.PHONY: hotfix-cluster
hotfix-cluster: ## Apply hotfix to all cluster nodes, skipping offline ones
	@$(MAKE) hotfix-rpi RPI_HOST=cocli5x0.local
	@$(MAKE) hotfix-rpi RPI_HOST=octoprint.local
	@$(MAKE) hotfix-rpi RPI_HOST=coclipi.local

# ==============================================================================
# Raspberry Pi Worker Management
# ==============================================================================
RPI_HOST ?= octoprint.local
RPI_USER ?= mstouffer
RPI_DIR ?= ~/repos/cocli

.PHONY: setup-rpi
setup-rpi: ## Bootstap the Raspberry Pi with Docker and Git
	scp scripts/setup_rpi.sh $(RPI_USER)@$(RPI_HOST):~/setup_rpi.sh
	ssh $(RPI_USER)@$(RPI_HOST) "chmod +x ~/setup_rpi.sh && ~/setup_rpi.sh"

.PHONY: boardcheck
boardcheck: ## Copy boardcheck.sh to the Pi and run it
	scp docker/rpi-worker/boardcheck.sh $(RPI_USER)@$(RPI_HOST):~/boardcheck.sh
	ssh $(RPI_USER)@$(RPI_HOST) "chmod +x ~/boardcheck.sh && ~/boardcheck.sh"

.PHONY: ssh-rpi
ssh-rpi: ## SSH into the Raspberry Pi worker
	ssh $(RPI_USER)@$(RPI_HOST)

.PHONY: check-rpi-voltage
check-rpi-voltage: ## Check Raspberry Pi for load, undervoltage and throttling issues
	@ssh $(RPI_USER)@$(RPI_HOST) "uptime; vcgencmd measure_volts; vcgencmd get_throttled" | while read line; do \
		echo "$$line"; \
		if [[ "$$line" == "throttled="* ]]; then \
			STATUS=$${line#*=}; \
			echo "Decoding Status: $$STATUS"; \
			if [ "$$((STATUS & 0x1))" -ne 0 ]; then echo "  [CRITICAL] Undervoltage detected NOW"; fi; \
			if [ "$$((STATUS & 0x2))" -ne 0 ]; then echo "  [CRITICAL] Frequency capped NOW"; fi; \
			if [ "$$((STATUS & 0x4))" -ne 0 ]; then echo "  [WARNING] Throttled NOW"; fi; \
			if [ "$$((STATUS & 0x8))" -ne 0 ]; then echo "  [WARNING] Soft temperature limit reached NOW"; fi; \
			if [ "$$((STATUS & 0x10000))" -ne 0 ]; then echo "  [HISTORY] Undervoltage has occurred since boot"; fi; \
			if [ "$$((STATUS & 0x20000))" -ne 0 ]; then echo "  [HISTORY] Frequency capping has occurred since boot"; fi; \
			if [ "$$((STATUS & 0x40000))" -ne 0 ]; then echo "  [HISTORY] Throttling has occurred since boot"; fi; \
			if [ "$$((STATUS & 0x80000))" -ne 0 ]; then echo "  [HISTORY] Soft temperature limit reached since boot"; fi; \
			if [ "$$STATUS" == "0x0" ]; then echo "  [OK] Power status is healthy."; fi; \
		fi; \
	done

.PHONY: check-cluster-health
check-cluster-health: ## Check health (load/voltage) of all known Raspberry Pi workers
	@$(VENV_DIR)/bin/python scripts/check_cluster_health.py

.PHONY: shutdown-rpi
shutdown-rpi: ## Safely shut down the Raspberry Pi (halts system)
	@echo "Shutting down $(RPI_HOST)..."
	-ssh $(RPI_USER)@$(RPI_HOST) "sudo shutdown -h now"

.PHONY: check-git-sync
check-git-sync: ## Verify that the local git repo is clean and synced with upstream
	@if [ -n "$$(git status --porcelain)" ]; then \
		printf "\033[0;31mError: You have uncommitted changes. Please commit them first.\033[0m\n"; \
		git status --porcelain; \
		exit 1; \
	fi
	@if [ -n "$$(git log @{u}..HEAD --oneline)" ]; then \
		printf "\033[0;31mError: You have unpushed commits. Please push them to origin first.\033[0m\n"; \
		git log @{u}..HEAD --oneline; \
		exit 1; \
	fi
	@printf "\033[0;32mGit status is clean and synced.\033[0m\n"

.PHONY: build-rpi-base
build-rpi-base: check-git-sync ## Build the heavy base Docker image on RPi (Run once/rarely)
	ssh $(RPI_USER)@$(RPI_HOST) "cd $(RPI_DIR) && git fetch --all && git reset --hard origin/main && docker build -t integrator/cocli-rpi-base:latest -f docker/rpi-worker/Dockerfile.base ."

.PHONY: push-rpi-base
push-rpi-base: ## Push the base image to Docker Hub
	ssh $(RPI_USER)@$(RPI_HOST) "docker push integrator/cocli-rpi-base:latest"

.PHONY: rebuild-rpi-worker
rebuild-rpi-worker: test check-git-sync ## Pull latest code and rebuild Docker image on Raspberry Pi
	@echo "Stopping existing containers on $(RPI_HOST) to free resources for build..."
	-ssh $(RPI_USER)@$(RPI_HOST) "docker stop \$$(docker ps -q --filter name=cocli-) 2>/dev/null || true"
	ssh $(RPI_USER)@$(RPI_HOST) "cd $(RPI_DIR) && git fetch --all && git reset --hard origin/main && docker build --no-cache -t cocli-worker-rpi -f docker/rpi-worker/Dockerfile ."

.PHONY: start-rpi-worker
start-rpi-worker: ## Start the Docker worker on Raspberry Pi
	$(eval SCRAPE_QUEUE := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_scrape_tasks_queue_url', ''))"))
	$(eval DETAILS_QUEUE := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_gm_list_item_queue_url', ''))"))
	ssh $(RPI_USER)@$(RPI_HOST) "docker run -d --restart always --name cocli-scraper-worker \
		--shm-size=2gb \
		-e TZ=America/Los_Angeles \
		-e CAMPAIGN_NAME='$(CAMPAIGN)' \
		-e AWS_PROFILE=$(AWS_PROFILE) \
		-e COCLI_SCRAPE_TASKS_QUEUE_URL='$(SCRAPE_QUEUE)' \
		-e COCLI_GM_LIST_ITEM_QUEUE_URL='$(DETAILS_QUEUE)' \
		-v ~/.aws:/root/.aws:ro cocli-worker-rpi:latest cocli worker gm-list --workers $(SCRAPE_WORKERS)"

.PHONY: start-rpi-details-worker
start-rpi-details-worker: ## Start the Details Worker on Raspberry Pi
	$(eval DETAILS_QUEUE := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_gm_list_item_queue_url', ''))"))
	$(eval ENRICHMENT_QUEUE := $(shell ./.venv/bin/python -c "from cocli.core.config import load_campaign_config; print(load_campaign_config('$(CAMPAIGN)').get('aws', {}).get('cocli_enrichment_queue_url', ''))"))
	ssh $(RPI_USER)@$(RPI_HOST) "docker run -d --restart always --name cocli-details-worker \
		--shm-size=2gb \
		-e TZ=America/Los_Angeles \
		-e CAMPAIGN_NAME='$(CAMPAIGN)' \
		-e AWS_PROFILE=$(AWS_PROFILE) \
		-e COCLI_GM_LIST_ITEM_QUEUE_URL='$(DETAILS_QUEUE)' \
		-e COCLI_ENRICHMENT_QUEUE_URL='$(ENRICHMENT_QUEUE)' \
		-v ~/.aws:/root/.aws:ro cocli-worker-rpi:latest cocli worker gm-details --workers $(DETAILS_WORKERS)"

start-rpi-enrichment-worker: ## Start the Enrichment Worker on Raspberry Pi
	$(eval AWS_PROFILE_ENV := $(if $(AWS_PROFILE),-e AWS_PROFILE=$(AWS_PROFILE),))
	ssh $(RPI_USER)@$(RPI_HOST) "docker run -d --restart always --name cocli-enrichment-worker \
		--shm-size=2gb \
		-e TZ=America/Los_Angeles \
		-e CAMPAIGN_NAME='$(CAMPAIGN)' \
		$(AWS_PROFILE_ENV) \
		-e COCLI_QUEUE_TYPE=filesystem \
		-v ~/repos/cocli_data:/app/cocli_data \
		-v ~/.aws:/root/.aws:ro cocli-worker-rpi:latest cocli worker enrichment --workers $(WORKERS)"

stop-rpi-enrichment-worker: ## Stop the Enrichment Worker on Raspberry Pi
	-ssh $(RPI_USER)@$(RPI_HOST) "docker stop cocli-enrichment-worker && docker rm cocli-enrichment-worker"

.PHONY: stop-rpi-worker
stop-rpi-worker: ## Stop and remove the Docker worker on Raspberry Pi
	-ssh $(RPI_USER)@$(RPI_HOST) "docker stop cocli-scraper-worker && docker rm cocli-scraper-worker"

.PHONY: stop-rpi-details-worker
stop-rpi-details-worker: ## Stop and remove the Details worker on Raspberry Pi
	-ssh $(RPI_USER)@$(RPI_HOST) "docker stop cocli-details-worker && docker rm cocli-details-worker"

.PHONY: restart-rpi-worker
restart-rpi-worker: stop-rpi-worker start-rpi-worker ## Restart the Raspberry Pi worker

.PHONY: start-rpi-supervisor
start-rpi-supervisor: ## Start the Supervisor on Raspberry Pi for dynamic scaling
	ssh $(RPI_USER)@$(RPI_HOST) "docker run -d --restart always --name cocli-supervisor \
		--shm-size=2gb \
		-e TZ=America/Los_Angeles \
		-e CAMPAIGN_NAME='$(CAMPAIGN)' \
		-e AWS_PROFILE=$(AWS_PROFILE) \
		-e COCLI_HOSTNAME=\$$(hostname) \
		-e COCLI_QUEUE_TYPE=filesystem \
		-v ~/repos/cocli_data:/app/cocli_data \
		-v ~/.aws:/root/.aws:ro cocli-worker-rpi:latest cocli worker supervisor --debug"

.PHONY: restart-rpi-all
restart-rpi-all: ## Restart all Raspberry Pi workers using supervisor on all nodes
	-$(MAKE) stop-rpi-all
	$(MAKE) start-rpi-supervisor RPI_HOST=octoprint.local
	$(MAKE) start-rpi-supervisor RPI_HOST=coclipi.local
	$(MAKE) start-rpi-supervisor RPI_HOST=cocli5x0.local

.PHONY: deploy-cluster
deploy-cluster: ## Rebuild and restart the entire cluster with Supervisor
	@echo "Deploying to all nodes..."
	$(MAKE) rebuild-rpi-worker RPI_HOST=octoprint.local
	$(MAKE) rebuild-rpi-worker RPI_HOST=coclipi.local
	$(MAKE) rebuild-rpi-worker RPI_HOST=cocli5x0.local
	$(MAKE) restart-rpi-all
	@echo "Cluster deployment complete. All nodes running Supervisor."

.PHONY: shutdown-cluster
shutdown-cluster: ## Safely shut down all Raspberry Pi workers
	@echo "Shutting down octoprint.local..."
	-$(MAKE) shutdown-rpi RPI_HOST=octoprint.local
	@echo "Shutting down coclipi.local..."
	-$(MAKE) shutdown-rpi RPI_HOST=coclipi.local
	@echo "Shutting down cocli5x0.local..."
	-$(MAKE) shutdown-rpi RPI_HOST=cocli5x0.local
	@echo "Shutdown commands sent. You can safely unplug the Pis in 30 seconds."

.PHONY: log-rpi-worker
log-rpi-worker: ## Tail logs from the Raspberry Pi List Scraper worker
	ssh $(RPI_USER)@$(RPI_HOST) "docker logs -n 100 cocli-scraper-worker"

.PHONY: log-rpi-details-worker
log-rpi-details-worker: ## Tail logs from the Raspberry Pi Details Scraper worker
	ssh $(RPI_USER)@$(RPI_HOST) "docker logs -n 100 cocli-details-worker"

.PHONY: log-rpi-all
log-rpi-all: ## Tail logs from all Raspberry Pi cocli worker containers
	ssh $(RPI_USER)@$(RPI_HOST) "docker ps --filter name=cocli- --format '{{.Names}}' | xargs -I {} docker logs -n 100 {}"

.PHONY: clean-docker-pi
clean-docker-pi: ## Remove all stopped containers, unused networks, dangling images, and build cache on Raspberry Pi
	@echo "Cleaning up Docker system on Raspberry Pi..."
	ssh $(RPI_USER)@$(RPI_HOST) "docker system prune -f"

.PHONY: stop-rpi
stop-rpi: ## Stop all cocli worker containers on a single RPi (Usage: make stop-rpi RPI_HOST=xxx.local)
	-ssh $(RPI_USER)@$(RPI_HOST) "if [ -n \"\$$(docker ps -q --filter name=cocli-)\" ]; then docker stop \$$(docker ps -q --filter name=cocli-); fi; if [ -n \"\$$(docker ps -a -q --filter name=cocli-)\" ]; then docker rm \$$(docker ps -a -q --filter name=cocli-); fi"

.PHONY: stop-rpi-all
stop-rpi-all: ## Stop all cocli worker containers on ALL cluster nodes
	-$(MAKE) stop-rpi RPI_HOST=octoprint.local
	-$(MAKE) stop-rpi RPI_HOST=coclipi.local
	-$(MAKE) stop-rpi RPI_HOST=cocli5x0.local

.PHONY: deploy-rpi
deploy-rpi: test deploy-creds-rpi stop-rpi rebuild-rpi-worker start-rpi-worker start-rpi-details-worker ## Full deployment: stop, rebuild, and restart both workers on a single RPi
	$(VENV_DIR)/bin/ruff check cocli/

missing-keywords: ## List the companies that are missing keywords to CSV
	$(VENV_DIR)/bin/python scripts/list_companies_missing_keywords.py --campaign $(CAMPAIGN)

.PHONY: keywords-report
keywords-report: sync-companies compile-companies ## Sync, compile, and generate both keyword reports
	$(VENV_DIR)/bin/python scripts/list_companies_with_keywords.py --campaign $(CAMPAIGN)
	$(VENV_DIR)/bin/python scripts/list_companies_missing_keywords.py --campaign $(CAMPAIGN)

refresh-keyword-display: ## Sync keyword server data and generate web report
	@echo "Syncing data and updating web report"
	$(MAKE) sync-companies
	$(MAKE) export-emails
	$(MAKE) web-deploy


show-kmls: ## Show KML files online (Usage: make show-kmls [BUCKET=cocli-web-assets] [PROFILE=bizkite-support])
	aws s3 ls s3://$(or $(BUCKET), cocli-web-assets)/kml/ --profile $(or $(PROFILE), bizkite-support)
