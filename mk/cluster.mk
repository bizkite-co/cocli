# Cluster Management & Deployment

RPI_HOST ?= cocli5x0.local
RPI_USER ?= mstouffer
CLUSTER_NODES = cocli5x0.local octoprint.local coclipi.local

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

