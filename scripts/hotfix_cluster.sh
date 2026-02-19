#!/bin/bash
# Verifiable Cluster Hotfix Script (Registry-Aware Edition)

RPI_USER="mstouffer"
CAMPAIGN_OVERRIDE=$2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# 1. Resolve Cluster Config from cocli_config.toml
CONFIG_FILE="data/config/cocli_config.toml"
REGISTRY_HOST=$(python3 -c "import toml; c = toml.load('$CONFIG_FILE'); print(c.get('cluster', {}).get('registry_host', ''))")
REGISTRY_URL="${REGISTRY_HOST}:5000"

get_node_campaign() {
    local host=$1
    if [ -n "$CAMPAIGN_OVERRIDE" ]; then
        echo "$CAMPAIGN_OVERRIDE"
        return
    fi
    # Try to resolve from global config first
    local campaign=$(python3 -c "import toml; c = toml.load('$CONFIG_FILE'); nodes = c.get('cluster', {}).get('nodes', []); print(next((n['campaign'] for n in nodes if n['host'] == '$host'), ''))")
    
    if [ -z "$campaign" ]; then
        # Fallback to docker inspection
        campaign=$(ssh $RPI_USER@$host "docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' cocli-supervisor 2>/dev/null" | grep CAMPAIGN_NAME | cut -d'=' -f2)
    fi
    echo "${campaign:-roadmap}"
}

verify_node() {
    local host=$1
    local node_campaign=$(get_node_campaign $host)

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
    local image_name="cocli-worker-rpi:latest"
    local registry_image="${REGISTRY_URL}/${image_name}"

    printf "[${BLUE}HOTFIX${NC}] Target: $host (Campaign: $node_campaign)\n"

    # 1. Sync Code
    printf "  [SYNC] Syncing repository to $host...\n"
    ssh $RPI_USER@$host "mkdir -p ~/repos/cocli_build"
    rsync -az --delete \
        --exclude '.venv' \
        --exclude '.git' \
        --exclude 'data' \
        --exclude '.logs' \
        --exclude '.pytest_cache' \
        ./ $RPI_USER@$host:~/repos/cocli_build/

    # 2. Signature Check
    printf "  [SIGNATURE] Checking code state...\n"
    local needs_build=$(ssh $RPI_USER@$host "cd ~/repos/cocli_build && python3 scripts/check_code_signature.py --check --task docker_build && echo 'SKIP' || echo 'BUILD'")
    
    if [ "$needs_build" == "BUILD" ]; then
        if [ "$host" == "$REGISTRY_HOST" ]; then
            printf "  [BUILD] Hub node changed. Running Docker build...\n"
            ssh $RPI_USER@$host "cd ~/repos/cocli_build && docker build -t $image_name -f docker/rpi-worker/Dockerfile . && docker tag $image_name $registry_image && docker push $registry_image && python3 scripts/check_code_signature.py --update --task docker_build"
        else
            printf "  [PULL] Code changed. Pulling from registry hub ($REGISTRY_HOST)...\n"
            if ssh $RPI_USER@$host "docker pull $registry_image && docker tag $registry_image $image_name"; then
                # Update signature locally so we know we are in sync with the hub
                rsync -az .code_signatures.json $RPI_USER@$host:~/repos/cocli_build/
            else
                printf "  [WARN] Pull failed. Falling back to local build on $host...\n"
                ssh $RPI_USER@$host "cd ~/repos/cocli_build && docker build -t $image_name -f docker/rpi-worker/Dockerfile . && python3 scripts/check_code_signature.py --update --task docker_build"
            fi
        fi
    else
        printf "  [SKIP] Code identical to last build. Skipping image update.\n"
    fi

    # 3. Restart
    printf "  [RESTART] Swapping container...\n"
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
        $image_name \
        cocli worker supervisor --debug" >/dev/null
    
    # 4. Verify
    verify_node $host
}

target=$1
if [ -n "$target" ]; then
    hotfix_node $target
else
    # Deploy to ALL nodes in global config
    nodes=$(python3 -c "import toml; c = toml.load('$CONFIG_FILE'); nodes = c.get('cluster', {}).get('nodes', []); print(' '.join([n['host'] for n in nodes]))")
    
    # ALWAYS do Registry Host first to ensure image is available
    if [[ "$nodes" == *"$REGISTRY_HOST"* ]]; then
        hotfix_node $REGISTRY_HOST
    fi

    for node in $nodes; do
        if [ "$node" != "$REGISTRY_HOST" ]; then
            hotfix_node $node
        fi
    done
fi
