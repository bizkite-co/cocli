#!/bin/bash
# Verifiable Cluster Hotfix Script (Sticky Campaign Edition)

RPI_USER="mstouffer"
# DEFAULT_CLUSTER_NODES are now resolved from mk/cluster.mk or passed as target
CAMPAIGN_OVERRIDE=$2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

get_node_campaign() {
    local host=$1
    # 1. If override provided, use it
    if [ -n "$CAMPAIGN_OVERRIDE" ]; then
        echo "$CAMPAIGN_OVERRIDE"
        return
    fi
    
    # 2. Try to get from existing container
    local existing=$(ssh $RPI_USER@$host "docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' cocli-supervisor 2>/dev/null" | grep CAMPAIGN_NAME | cut -d'=' -f2)
    if [ -n "$existing" ]; then
        echo "$existing"
        return
    fi
    
    # 3. Default fallback
    echo "roadmap"
}

verify_node() {
    local host=$1
    local short_name=$(echo $host | cut -d'.' -f1)
    local node_campaign=$(get_node_campaign $host)

    # Resolve IOT_PROFILE from config
    local iot_profile=$(python3 -c "from cocli.core.config import load_campaign_config; c = load_campaign_config('$node_campaign'); profiles = c.get('aws', {}).get('iot_profiles', []); print(profiles[0] if profiles else '')")
    if [ -z "$iot_profile" ]; then
        printf "[${RED}ERROR${NC}] IOT_PROFILE not found in config for $node_campaign\n"
        return 1
    fi

    printf "[${BLUE}VERIFY${NC}] Checking $host stability and heartbeats (Campaign: $node_campaign)...\n"
    sleep 15
    
    # 1. Check for success marker
    if ssh $RPI_USER@$host "docker logs --since 30s cocli-supervisor 2>&1" | grep -q "Supervisor started"; then
        printf "[${GREEN}SUCCESS${NC}] $host is stable. Supervisor started.\n"
        
        # 2. DEEP VERIFY: Check S3
        local bucket="${node_campaign}-cocli-data-use1"
        now=$(date -u +%s)
        last_mod_str=$(aws s3api head-object --bucket $bucket --key status/$short_name.json --profile $iot_profile --query 'LastModified' --output text 2>/dev/null)
        
        if [ -n "$last_mod_str" ]; then
            last_mod=$(date -d "$last_mod_str" -u +%s)
            diff=$((now - last_mod))
            if [ $diff -lt 120 ]; then
                printf "[${GREEN}ONLINE${NC}] Fresh heartbeat confirmed on S3 (updated ${diff}s ago)\n"
                return 0
            else
                printf "[${RED}STALE${NC}] Heartbeat file exists but is stale ($diff seconds old).\n"
                return 1
            fi
        else
            printf "[${RED}OFFLINE${NC}] No heartbeat file found on S3 for $short_name yet.\n"
            return 1
        fi
    else
        # Report crash
        error=$(ssh $RPI_USER@$host "docker logs --since 30s cocli-supervisor 2>&1" | grep -iE "Traceback|SyntaxError|ImportError|ModuleNotFoundError")
        printf "[${RED}CRITICAL${NC}] Crash detected on $host!\n"
        printf "$error\n"
        return 1
    fi
}

hotfix_node() {
    local host=$1
    local short_name=$(echo $host | cut -d'.' -f1)
    local node_campaign=$(get_node_campaign $host)

    # Resolve IOT_PROFILE from config
    local iot_profile=$(python3 -c "from cocli.core.config import load_campaign_config; c = load_campaign_config('$node_campaign'); profiles = c.get('aws', {}).get('iot_profiles', []); print(profiles[0] if profiles else '')")
    if [ -z "$iot_profile" ]; then
        printf "[${RED}ERROR${NC}] IOT_PROFILE not found in config for $node_campaign\n"
        return 1
    fi

    printf "[${BLUE}HOTFIX${NC}] Deploying to $host (Campaign: $node_campaign)...\n"
    
    # 1. Stop and Maintenance
    ssh $RPI_USER@$host "docker stop cocli-supervisor && docker rm cocli-supervisor" >/dev/null 2>&1
    ssh $RPI_USER@$host "docker run -d --name cocli-supervisor --shm-size=2gb -e TZ=America/Los_Angeles -e CAMPAIGN_NAME='$node_campaign' -e COCLI_QUEUE_TYPE=filesystem -v ~/repos/data:/app/data -v ~/.aws:/root/.aws:ro -v ~/.cocli:/root/.cocli:ro --entrypoint sleep cocli-worker-rpi:latest infinity" >/dev/null
    
    # 2. Wipe dist-packages and /app
    ssh $RPI_USER@$host "docker exec cocli-supervisor bash -c 'rm -rf /usr/local/lib/python3.12/dist-packages/cocli /app/cocli /app/build'" >/dev/null 2>&1
    
    # 3. Push and Symlink
    ssh $RPI_USER@$host "mkdir -p /tmp/cocli_hotfix"
    scp -qr cocli scripts VERSION pyproject.toml $RPI_USER@$host:/tmp/cocli_hotfix/
    ssh $RPI_USER@$host "docker cp /tmp/cocli_hotfix/. cocli-supervisor:/app/"
    
    # FORCED SYMLINK: Make dist-packages point directly to our hotfixed code
    ssh $RPI_USER@$host "docker exec cocli-supervisor bash -c 'rm -rf /usr/local/lib/python3.12/dist-packages/cocli && ln -s /app/cocli /usr/local/lib/python3.12/dist-packages/cocli'"
    
    # 4. Restore Real Entrypoint
    ssh $RPI_USER@$host "docker stop cocli-supervisor && docker rm cocli-supervisor" >/dev/null
    ssh $RPI_USER@$host "docker run -d --restart always --name cocli-supervisor --shm-size=2gb -e TZ=America/Los_Angeles -e CAMPAIGN_NAME='$node_campaign' -e COCLI_HOSTNAME=$short_name -e COCLI_QUEUE_TYPE=filesystem -v ~/repos/data:/app/data -v ~/.aws:/root/.aws:ro -v ~/.cocli:/root/.cocli:ro cocli-worker-rpi:latest cocli worker supervisor --debug" >/dev/null
    
    # 5. Verify
    verify_node $host
    return $?
}

# --- Execution ---
target=$1
if [ -n "$target" ]; then
    hotfix_node $target
else
    # Resolve CLUSTER_NODES from campaign config
    campaign=${CAMPAIGN_OVERRIDE:-roadmap}
    nodes=$(python3 -c "
from cocli.core.config import load_campaign_config
c = load_campaign_config('$campaign')
scaling = c.get('prospecting', {}).get('scaling', {})
# Filter for nodes ending in .pi or known node names
print(' '.join([k for k in scaling.keys() if k != 'fargate']))
")
    
    if [ -z "$nodes" ]; then
        printf "[${RED}ERROR${NC}] No nodes found in config for campaign: $campaign\n"
        exit 1
    fi
    
    for node in $nodes; do
        # Ensure we have the .pi suffix if missing from config key
        if [[ ! "$node" == *".pi" ]]; then
            node="${node}.pi"
        fi
        hotfix_node $node
    done
fi
