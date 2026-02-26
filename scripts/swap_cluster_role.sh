#!/bin/bash
# Role-Aware Cluster Swapper

RPI_USER="mstouffer"
ROLE=${1:-scraper}

# 1. Resolve Cluster Config
CONFIG_FILE="data/config/cocli_config.toml"
nodes=$(python3 -c "import toml; c = toml.load('$CONFIG_FILE'); nodes = c.get('cluster', {}).get('nodes', []); print(' '.join([n['host'] for n in nodes]))")

for host in $nodes; do
    if [ "$host" == "octoprint.pi" ]; then continue; fi
    
    printf "--- Swapping %s to ROLE: %s ---\n" "$host" "$ROLE"
    short_name=$(echo $host | cut -d'.' -f1)
    
    # Try to resolve campaign from config
    node_campaign=$(python3 -c "import toml; c = toml.load('$CONFIG_FILE'); nodes = c.get('cluster', {}).get('nodes', []); print(next((n['campaign'] for n in nodes if n['host'] == '$host'), 'roadmap'))")

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
        cocli worker gm-details --role $ROLE --debug" >/dev/null
    
    printf "  [DONE] %s is now a %s\n" "$host" "$ROLE"
done
