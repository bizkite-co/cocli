# Cluster Management & Deployment

RPI_HOST ?= coclipi.pi
RPI_USER ?= mstouffer

# Resolve authorized nodes from campaign config
CLUSTER_NODES = $(shell python3 -c "from cocli.core.config import load_campaign_config; c = load_campaign_config('$(CAMPAIGN)'); scaling = c.get('prospecting', {}).get('scaling', {}); print(' '.join([ (k if k.endswith('.pi') else k+'.pi') for k in scaling.keys() if k != 'fargate']))" 2>/dev/null)

.PHONY: hotfix-cluster-safe log-rpi-all cluster-status

hotfix-cluster-safe: ## Perform a safe, verifiable cluster-wide hotfix
	@chmod +x scripts/hotfix_cluster.sh
	@./scripts/hotfix_cluster.sh

hotfix-one-safe: ## Perform a safe hotfix on a single node (Usage: make hotfix-one-safe RPI_HOST=xxx.local)
	@chmod +x scripts/hotfix_cluster.sh
	@./scripts/hotfix_cluster.sh $(RPI_HOST)

log-rpi-all: ## Tail logs from all Raspberry Pi containers
	@for node in $(CLUSTER_NODES); do \
		printf "\033[1;34m--- Logs: %s ---\033[0m\n" "$$node"; \
		ssh $(RPI_USER)@$$node "docker logs --tail 20 cocli-supervisor" 2>/dev/null || true; \
	done

cluster-status: ## Check the status of all cluster nodes
	@for node in $(CLUSTER_NODES); do \
		status=$$(ssh $(RPI_USER)@$$node "docker inspect -f '{{.State.Status}}' cocli-supervisor 2>/dev/null" || echo "offline"); \
		printf "% -20s: %s\n" "$$node" "$$status"; \
	done

