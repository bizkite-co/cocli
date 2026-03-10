#!/bin/bash
# Verifiable Cluster Hotfix Script (Registry-Aware, IP-Based)

RPI_USER="mstouffer"
CAMPAIGN_OVERRIDE=$2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# 1. Resolve Cluster Config
CONFIG_FILE="data/config/cocli_config.toml"
# We use the IP address for the registry to avoid hostname resolution issues on child nodes
REGISTRY_IP="10.0.0.17"
REGISTRY_HOST="cocli5x1.pi"
REGISTRY_URL="${REGISTRY_IP}:5000"

get_node_campaign() {
    local host=$1
    if [ -n "$CAMPAIGN_OVERRIDE" ]; then
        echo "$CAMPAIGN_OVERRIDE"
        return
    fi
    local campaign=$(python3 -c "import toml; c = toml.load('$CONFIG_FILE'); nodes = c.get('cluster', {}).get('nodes', []); default = c.get('campaign', {}).get('name', 'roadmap'); print(next((n.get('campaign', default) for n in nodes if n['host'] == '$host'), default))")
    echo "${campaign:-roadmap}"
}

verify_node() {
    local host=$1
    local node_campaign=$(get_node_campaign $host)

    printf "[${BLUE}VERIFY${NC}] Checking $host stability (Campaign: $node_campaign)...\n"
    # Give it a bit more time to initialize
    sleep 20
    
    if ! ssh $RPI_USER@$host "docker ps --format '{{.Names}}' | grep -q cocli-supervisor"; then
        printf "[${RED}ERROR${NC}] $host supervisor container is NOT running.\n"
        return 1
    fi

    local logs=$(ssh $RPI_USER@$host "docker logs --tail 100 cocli-supervisor 2>&1")
    local has_errors=$(echo "$logs" | grep -Ei "ERROR|Traceback|Exception" | grep -v "S3 Lease Error" | grep -v "HeadScraper error" | head -n 3)
    # Success indicators for both scraper and orchestrator modes
    local has_success=$(echo "$logs" | grep -Ei "Extracted|S3 Ack|Polling|Task found|Gossip Bridge started|WorkerService: Starting|acquired S3 lease|WARMUP: Navigating|Processing Details|Starting machine" | head -n 1)

    if [ -n "$has_errors" ]; then
        printf "[${RED}WARN${NC}] Errors detected in $host logs:\n$has_errors\n"
    fi

    if [ -n "$has_success" ]; then
        printf "[${GREEN}SUCCESS${NC}] $host is functional (Verified by logs).\n"
        return 0
    else
        printf "[${RED}ERROR${NC}] $host is running but NO activity detected in logs.\n"
        return 1
    fi
}

hotfix_node() {
    local host=$1
    local short_name=$(echo $host | cut -d'.' -f1)
    local node_campaign=$(get_node_campaign $host)
    local image_name="cocli-worker-rpi:latest"
    local registry_image="${REGISTRY_URL}/${image_name}"

    printf "[${BLUE}HOTFIX${NC}] Target: $host (Campaign: $node_campaign)\n"

    # 1. Sync Code (Required for builds or signatures)
    printf "  [SYNC] Syncing repository to $host...\n"
    ssh $RPI_USER@$host "mkdir -p ~/repos/cocli_build"
    rsync -az --delete \
        --exclude '.venv' \
        --exclude '.git' \
        --exclude 'data' \
        --exclude '.logs' \
        --exclude '.pytest_cache' \
        ./ $RPI_USER@$host:~/repos/cocli_build/

    # 2. Build or Pull
    if [ "$host" == "$REGISTRY_HOST" ]; then
        printf "  [BUILD] Hub node. Running Docker build...\n"
        ssh $RPI_USER@$host "cd ~/repos/cocli_build && docker build -t $image_name -f docker/rpi-worker/Dockerfile . && python3 scripts/check_code_signature.py --update --task docker_build"
    else
        printf "  [PULL] Child node. Pulling from verified registry ($REGISTRY_URL)...\n"
        if ! ssh $RPI_USER@$host "docker pull $registry_image && docker tag $registry_image $image_name"; then
            printf "  [WARN] Pull failed. Falling back to local build on $host...\n"
            ssh $RPI_USER@$host "cd ~/repos/cocli_build && docker build -t $image_name -f docker/rpi-worker/Dockerfile . && python3 scripts/check_code_signature.py --update --task docker_build"
        fi
    fi

    # 3. Restart
    printf "  [RESTART] Swapping container...\n"
    ssh $RPI_USER@$host "docker stop cocli-supervisor && docker rm cocli-supervisor" >/dev/null 2>&1
    
    ssh $RPI_USER@$host "docker run -d --restart always --name cocli-supervisor \
        --shm-size=2gb \
        -e TZ=America/Los_Angeles \
        -e CAMPAIGN_NAME='$node_campaign' \
        -e AWS_PROFILE='${node_campaign}-iot' \
        -e COCLI_HOSTNAME=$short_name \
        -e COCLI_QUEUE_TYPE=filesystem \
        -v ~/repos/data:/app/data \
        -v ~/.aws:/root/.aws:ro \
        -v ~/.cocli:/root/.cocli:ro \
        $image_name \
        cocli worker orchestrate --debug" >/dev/null
    
    # 4. Verify
    if verify_node $host; then
        # 5. IF Hub was verified, push to registry so others can pull this stable version
        if [ "$host" == "$REGISTRY_HOST" ]; then
            printf "  [PUBLISH] Hub verified stable. Pushing to local registry...\n"
            ssh $RPI_USER@$host "docker tag $image_name $registry_image && docker push $registry_image"
        fi
        return 0
    else
        return 1
    fi
}

target=$1
nodes=$(python3 -c "import toml; c = toml.load('$CONFIG_FILE'); nodes = c.get('cluster', {}).get('nodes', []); print(' '.join([n['host'] for n in nodes]))")

if [ "$target" == "--children" ]; then
    for node in $nodes; do
        if [ "$node" != "$REGISTRY_HOST" ]; then
            hotfix_node $node
        fi
    done
elif [ -n "$target" ]; then
    hotfix_node $target
else
    # Default: Staged Rollout
    # 1. Hub First
    if ! hotfix_node $REGISTRY_HOST; then
        printf "[${RED}FATAL${NC}] Hub verification failed. Aborting cluster rollout.\n"
        exit 1
    fi

    # 2. Children Next
    for node in $nodes; do
        if [ "$node" != "$REGISTRY_HOST" ]; then
            hotfix_node $node
        fi
    done
fi
