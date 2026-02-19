# Cluster Management & Deployment

RPI_HOST ?= coclipi.pi
RPI_USER ?= mstouffer
REGISTRY_HOST ?= cocli5x1.pi

# Resolve authorized nodes from global config
CLUSTER_NODES = $(shell python3 -c "import toml; c = toml.load('data/config/cocli_config.toml'); nodes = c.get('cluster', {}).get('nodes', []); print(' '.join([n['host'] for n in nodes]))" 2>/dev/null)

.PHONY: hotfix-cluster-safe log-rpi-all cluster-status setup-registry configure-cluster-registry configure-cluster-hosts

setup-registry: ## Setup local Docker registry on the registry host
	@scp scripts/setup_local_registry.sh $(RPI_USER)@$(REGISTRY_HOST):/tmp/
	@ssh $(RPI_USER)@$(REGISTRY_HOST) "chmod +x /tmp/setup_local_registry.sh && /tmp/setup_local_registry.sh"

configure-cluster-registry: ## Configure all cluster nodes to trust the local registry
	@for node in $(CLUSTER_NODES); do \
		printf "\033[1;34m--- Configuring Registry: %s ---\033[0m\n" "$$node"; \
		scp scripts/configure_insecure_registry.sh $(RPI_USER)@$$node:/tmp/; \
		ssh $(RPI_USER)@$$node "chmod +x /tmp/configure_insecure_registry.sh && /tmp/configure_insecure_registry.sh $(REGISTRY_HOST):5000"; \
	done

configure-cluster-hosts: ## Propagate the IP-to-Hostname mapping to all cluster nodes (/etc/hosts)
	$(eval HOST_MAP_JSON := $(shell python3 -c "import toml, json; c = toml.load('data/config/cocli_config.toml'); nodes = c.get('cluster', {}).get('nodes', []); print(json.dumps({n['host']: n['ip'] for n in nodes}))" 2>/dev/null || echo "{}"))
	@for node in $(CLUSTER_NODES); do \
		printf "\033[1;34m--- Configuring Hosts: %s ---\033[0m\n" "$$node"; \
		bash scripts/configure_cluster_hosts.sh $$node '$(HOST_MAP_JSON)'; \
	done

hotfix-cluster-safe: ## Perform a safe, verifiable cluster-wide hotfix using local registry
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

