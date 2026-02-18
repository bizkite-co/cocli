#!/bin/bash
# Verifiable Cluster Hotfix Script (Direct Injection Edition)

RPI_USER="mstouffer"
CAMPAIGN_OVERRIDE=$2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

get_node_campaign() {
    local host=$1
    if [ -n "$CAMPAIGN_OVERRIDE" ]; then
        echo "$CAMPAIGN_OVERRIDE"
        return
    fi
    local existing=$(ssh $RPI_USER@$host "docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' cocli-supervisor 2>/dev/null" | grep CAMPAIGN_NAME | cut -d'=' -f2)
    echo "${existing:-roadmap}"
}

verify_node() {
    local host=$1
    local short_name=$(echo $host | cut -d'.' -f1)
    local node_campaign=$(get_node_campaign $host)

    local bucket=$(python3 -c "from cocli.core.config import load_campaign_config; c = load_campaign_config('$node_campaign'); print(c.get('aws', {}).get('data_bucket_name', ''))")
    local iot_profile=$(python3 -c "from cocli.core.config import load_campaign_config; c = load_campaign_config('$node_campaign'); profiles = c.get('aws', {}).get('iot_profiles', []); print(profiles[0] if profiles else '')")

    printf "[${BLUE}VERIFY${NC}] Checking $host stability (Campaign: $node_campaign)...\n"
    sleep 10
    
    if ssh $RPI_USER@$host "docker ps --format '{{.Names}}' | grep -q cocli-supervisor"; then
        printf "[${GREEN}SUCCESS${NC}] $host supervisor container is running.\n"
        return 0
    else
        printf "[${RED}ERROR${NC}] $host supervisor container is NOT running.\n"
        ssh $RPI_USER@$host "docker logs --tail 20 cocli-supervisor"
        return 1
    fi
}

hotfix_node() {
    local host=$1
    local short_name=$(echo $host | cut -d'.' -f1)
    local node_campaign=$(get_node_campaign $host)

    printf "[${BLUE}DEPLOY${NC}] Syncing and Building on $host (Campaign: $node_campaign)...\n"
    
    # 1. Sync the entire repository (excluding heavy/temp dirs)
    # We sync to a dedicated build directory on the host
    ssh $RPI_USER@$host "mkdir -p ~/repos/cocli_build"
    rsync -az --delete \
        --exclude '.venv' \
        --exclude '.git' \
        --exclude 'data' \
        --exclude '.logs' \
        --exclude '.pytest_cache' \
        ./ $RPI_USER@$host:~/repos/cocli_build/

    # 2. Perform Local Docker Build on the RPi
    # This leverages layer caching for pyproject.toml/uv.lock
    printf "[${BLUE}BUILD${NC}] Running Docker build on $host...\n"
    ssh $RPI_USER@$host "cd ~/repos/cocli_build && docker build -t cocli-worker-rpi:latest -f docker/rpi-worker/Dockerfile ."

    # 3. Stop and Restart with the fresh image
    printf "[${BLUE}RESTART${NC}] Swapping container on $host...\n"
    ssh $RPI_USER@$host "docker stop cocli-supervisor && docker rm cocli-supervisor" >/dev/null 2>&1
    
    ssh $RPI_USER@$host "docker run -d --restart always --name cocli-supervisor \
        --shm-size=2gb \
        -e TZ=America/Los_Angeles \
        -e CAMPAIGN_NAME='$node_campaign' \
        -e COCLI_HOSTNAME=$short_name \
        -e COCLI_QUEUE_TYPE=filesystem \
        -v ~/repos/data:/app/data \
        -v ~/.aws:/root/.aws:ro \
        -v ~/.cocli:/root/.cocli:ro \
        cocli-worker-rpi:latest \
        cocli worker supervisor --debug" >/dev/null
    
    # 4. Verify
    verify_node $host
}

target=$1
if [ -n "$target" ]; then
    hotfix_node $target
else
    campaign=${CAMPAIGN_OVERRIDE:-roadmap}
    nodes=$(python3 -c "from cocli.core.config import load_campaign_config; c = load_campaign_config('$campaign'); scaling = c.get('prospecting', {}).get('scaling', {}); print(' '.join([k for k in scaling.keys() if k != 'fargate']))")
    for node in $nodes; do
        [[ ! "$node" == *".pi" ]] && node="${node}.pi"
        hotfix_node $node
    done
fi
