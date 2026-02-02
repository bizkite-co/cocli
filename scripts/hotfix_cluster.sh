#!/bin/bash
# Verifiable Cluster Hotfix Script (Symlink Bypass Edition)

RPI_USER="mstouffer"
CLUSTER_NODES=("cocli5x0.pi" "octoprint.pi" "coclipi.pi" "cocli5x1.pi")

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

verify_node() {
    local host=$1
    local short_name=$(echo $host | cut -d'.' -f1)
    
    printf "[${BLUE}VERIFY${NC}] Checking $host stability and heartbeats...\n"
    sleep 15
    
    # 1. Check for success marker
    if ssh $RPI_USER@$host "docker logs --since 30s cocli-supervisor 2>&1" | grep -q "Supervisor started"; then
        printf "[${GREEN}SUCCESS${NC}] $host is stable. Supervisor started.\n"
        
        # 2. DEEP VERIFY: Check S3
        now=$(date -u +%s)
        last_mod_str=$(aws s3api head-object --bucket roadmap-cocli-data-use1 --key status/$short_name.json --profile westmonroe-support --query 'LastModified' --output text 2>/dev/null)
        
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
    printf "[${BLUE}HOTFIX${NC}] Deploying to $host...\n"
    
    # 1. Stop and Maintenance
    ssh $RPI_USER@$host "docker stop cocli-supervisor && docker rm cocli-supervisor" >/dev/null 2>&1
    ssh $RPI_USER@$host "docker run -d --name cocli-supervisor --shm-size=2gb -e TZ=America/Los_Angeles -e CAMPAIGN_NAME='roadmap' -e AWS_PROFILE=westmonroe-support -e COCLI_QUEUE_TYPE=filesystem -v ~/repos/data:/app/data -v ~/.aws:/root/.aws:ro --entrypoint sleep cocli-worker-rpi:latest infinity" >/dev/null
    
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
    ssh $RPI_USER@$host "docker run -d --restart always --name cocli-supervisor --shm-size=2gb -e TZ=America/Los_Angeles -e CAMPAIGN_NAME='roadmap' -e AWS_PROFILE=westmonroe-support -e COCLI_HOSTNAME=$short_name -e COCLI_QUEUE_TYPE=filesystem -v ~/repos/data:/app/data -v ~/.aws:/root/.aws:ro cocli-worker-rpi:latest cocli worker supervisor --debug" >/dev/null
    
    # 5. Verify
    verify_node $host
    return $?
}

# --- Execution ---
target=$1
if [ -n "$target" ]; then
    hotfix_node $target
else
    hotfix_node ${CLUSTER_NODES[0]}
fi
