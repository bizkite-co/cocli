

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
	uv sync --extra dev --extra full
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
	@./.venv/bin/python scripts/campaign_report.py $(CAMPAIGN)

coverage-gap: ## Generate a report of unscraped target areas
	@COCLI_DATA_HOME=$(shell pwd)/cocli_data ./.venv/bin/cocli campaign coverage-gap $(CAMPAIGN) --output coverage_gap.csv

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

.PHONY: publish-kml
publish-kml: install ## Generate and upload all KMLs (Coverage, Prospects, Customers) to S3
	$(VENV_DIR)/bin/cocli campaign publish-kml $(or $(CAMPAIGN), turboship)

.PHONY: ingest-prospects
ingest-prospects: install ## Ingest the existing google_maps_prospects.csv for the current campaign into the cache

.PHONY: ingest-existing-customers
ingest-existing-customers: install ## Ingest the existing customers.csv file into the cache
	$(VENV_DIR)/bin/cocli ingest-google-maps-csv /home/mstouffer/.local/share/cocli_data/scraped_data/turboship/customers/customers.csv

.PHONY: queue-scrape-tasks
queue-scrape-tasks: ## Queue scrape tasks for the 'turboship' campaign
	COCLI_DATA_HOME=$(shell pwd)/cocli_data uv run cocli campaign queue-scrapes turboship

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

.PHONY: watch-report
watch-report: ## Watch the campaign report every 5 seconds
	watch -n 5 -c "make report CAMPAIGN=$(CAMPAIGN)"

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
	cd cdk_scraper_deployment && uv venv && . .venv/bin/activate && uv pip install -r requirements.txt && cdk deploy --require-approval never --profile bizkite-support

.PHONY: deploy-enrichment
deploy-enrichment: test docker-build ## Build and deploy the enrichment service to AWS Fargate
	@./scripts/deploy_enrichment_service.sh

.PHONY: verify
verify: ## Verify the Fargate deployment
	@./scripts/verify_fargate_deployment.sh

force-update: ## Force Update of service
	aws ecs update-service --cluster ScraperCluster --service EnrichmentService --force-new-deployment --profile bizkite-support

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

.PHONY: sync-scraped-areas
sync-scraped-areas: ## Sync scraped areas from S3
	aws s3 sync s3://cocli-data-turboship/indexes/scraped_areas cocli_data/indexes/scraped_areas --profile bizkite-support

.PHONY: sync-prospects
sync-prospects: ## Sync prospects from S3
	aws s3 sync s3://cocli-data-turboship/campaigns/$(or $(CAMPAIGN), turboship)/indexes/google_maps_prospects cocli_data/campaigns/$(or $(CAMPAIGN), turboship)/indexes/google_maps_prospects --profile bizkite-support

.PHONY: sync-companies
sync-companies: install ## Sync enriched companies from S3
	$(VENV_DIR)/bin/cocli smart-sync companies

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
			echo "\033[0;31m[CRITICAL] Data is stale! Last scrape was $$hours hours ago.\033[0m"; \
			echo "File: $$filename"; \
		else \
			echo "\033[0;32m[OK] Data is fresh. Last scrape was $$hours hours ago.\033[0m"; \
			echo "File: $$filename"; \
		fi \
	fi

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
.PHONY: deploy-creds-rpi
deploy-creds-rpi: ## Securely deploy AWS credentials to the Raspberry Pi
	@if [ ! -f "docker/rpi-worker/.rpi_credentials" ] || [ ! -f "docker/rpi-worker/.rpi_config" ]; then \
		echo "\033[0;31mError: 'docker/rpi-worker/.rpi_credentials' and 'docker/rpi-worker/.rpi_config' files not found.\033[0m"; \
		echo "Please create them with the [bizkite-support] profile for the RPi in that directory."; \
		exit 1; \
	fi
	@echo "Deploying AWS credentials to $(RPI_USER)@$(RPI_HOST)..."
	ssh $(RPI_USER)@$(RPI_HOST) "rm -rf ~/.aws && mkdir ~/.aws"
	scp docker/rpi-worker/.rpi_credentials $(RPI_USER)@$(RPI_HOST):~/.aws/credentials
	scp docker/rpi-worker/.rpi_config $(RPI_USER)@$(RPI_HOST):~/.aws/config

# ==============================================================================
# Planning & Analysis
# ==============================================================================
.PHONY: generate-campaign-grid
generate-campaign-grid: install ## Generate 0.1-degree aligned grid for the current campaign
	COCLI_DATA_HOME=$(pwd)/cocli_data uv run cocli campaign generate-grid

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
	@echo "=== Checking octoprint.local (Scraper) ==="
	@$(MAKE) check-rpi-voltage RPI_HOST=octoprint.local
	@echo "\n=== Checking coclipi.local (Details) ==="
	@$(MAKE) check-rpi-voltage RPI_HOST=coclipi.local

.PHONY: shutdown-rpi
shutdown-rpi: ## Safely shut down the Raspberry Pi (halts system)
	@echo "Shutting down $(RPI_HOST)..."
	-ssh $(RPI_USER)@$(RPI_HOST) "sudo shutdown -h now"

.PHONY: check-git-sync
check-git-sync: ## Verify that the local git repo is clean and synced with upstream
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "\033[0;31mError: You have uncommitted changes. Please commit them first.\033[0m"; \
		git status --porcelain; \
		exit 1; \
	fi
	@if [ -n "$$(git log @{u}..HEAD --oneline)" ]; then \
		echo "\033[0;31mError: You have unpushed commits. Please push them to origin first.\033[0m"; \
		git log @{u}..HEAD --oneline; \
		exit 1; \
	fi
	@echo "\033[0;32mGit status is clean and synced.\033[0m"

.PHONY: build-rpi-base
build-rpi-base: check-git-sync ## Build the heavy base Docker image on RPi (Run once/rarely)
	ssh $(RPI_USER)@$(RPI_HOST) "cd $(RPI_DIR) && git fetch --all && git reset --hard origin/main && docker build -t integrator/cocli-rpi-base:latest -f docker/rpi-worker/Dockerfile.base ."

.PHONY: push-rpi-base
push-rpi-base: ## Push the base image to Docker Hub
	ssh $(RPI_USER)@$(RPI_HOST) "docker push integrator/cocli-rpi-base:latest"

.PHONY: rebuild-rpi-worker
rebuild-rpi-worker: check-git-sync ## Pull latest code and rebuild Docker image on Raspberry Pi
	ssh $(RPI_USER)@$(RPI_HOST) "cd $(RPI_DIR) && git fetch --all && git reset --hard origin/main && docker build --no-cache -t cocli-worker-rpi -f docker/rpi-worker/Dockerfile ."

.PHONY: start-rpi-worker
start-rpi-worker: ## Start the Docker worker on Raspberry Pi
	ssh $(RPI_USER)@$(RPI_HOST) "docker run -d --restart unless-stopped --name cocli-scraper-worker \
		-e TZ=America/Los_Angeles \
		-e COCLI_SCRAPE_TASKS_QUEUE_URL='$(COCLI_SCRAPE_TASKS_QUEUE_URL)' \
		-e COCLI_ENRICHMENT_QUEUE_URL='$(COCLI_ENRICHMENT_QUEUE_URL)' \
		-e COCLI_GM_LIST_ITEM_QUEUE_URL='$(COCLI_GM_LIST_ITEM_QUEUE_URL)' \
		-v ~/.aws:/root/.aws:ro cocli-worker-rpi:latest"

.PHONY: start-rpi-details-worker
start-rpi-details-worker: ## Start the Details Worker on Raspberry Pi
	ssh $(RPI_USER)@$(RPI_HOST) "docker run -d --restart unless-stopped --name cocli-details-worker \
		-e TZ=America/Los_Angeles \
		-e COCLI_SCRAPE_TASKS_QUEUE_URL='$(COCLI_SCRAPE_TASKS_QUEUE_URL)' \
		-e COCLI_ENRICHMENT_QUEUE_URL='$(COCLI_ENRICHMENT_QUEUE_URL)' \
		-e COCLI_GM_LIST_ITEM_QUEUE_URL='$(COCLI_GM_LIST_ITEM_QUEUE_URL)' \
		-v ~/.aws:/root/.aws:ro cocli-worker-rpi:latest cocli worker details"

.PHONY: stop-rpi-worker
stop-rpi-worker: ## Stop and remove the Docker worker on Raspberry Pi
	-ssh $(RPI_USER)@$(RPI_HOST) "docker stop cocli-scraper-worker && docker rm cocli-scraper-worker"

.PHONY: stop-rpi-details-worker
stop-rpi-details-worker: ## Stop and remove the Details worker on Raspberry Pi
	-ssh $(RPI_USER)@$(RPI_HOST) "docker stop cocli-details-worker && docker rm cocli-details-worker"

.PHONY: restart-rpi-worker
restart-rpi-worker: stop-rpi-worker start-rpi-worker ## Restart the Raspberry Pi worker

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

.PHONY: stop-rpi-all
stop-rpi-all: ## Stop all Raspberry Pi cocli worker containers
	-ssh $(RPI_USER)@$(RPI_HOST) "if [ -n \"\$$(docker ps -q --filter name=cocli-)\" ]; then docker stop \$$(docker ps -q --filter name=cocli-); fi; if [ -n \"\$$(docker ps -a -q --filter name=cocli-)\" ]; then docker rm \$$(docker ps -a -q --filter name=cocli-); fi"

.PHONY: deploy-rpi
deploy-rpi: stop-rpi-all rebuild-rpi-worker start-rpi-worker start-rpi-details-worker ## Full deployment: stop all, rebuild, and restart both workers

show-kmls: ## Show KML files online
	aws s3 ls s3://landing-page-turboheat-net/kml/ --profile bizkite-support
