#!/bin/bash
# Configure Docker to allow pushing to/pulling from an insecure local registry.
# Usage: ./configure_insecure_registry.sh <registry_host_and_port>
# Example: ./configure_insecure_registry.sh cocli5x1.pi:5000

set -e

REGISTRY_URL=$1

if [ -z "$REGISTRY_URL" ]; then
    echo "Usage: $0 <registry_host_and_port>"
    exit 1
fi

DAEMON_JSON="/etc/docker/daemon.json"

echo "Configuring insecure registry: $REGISTRY_URL"

# 1. Read existing config or initialize empty JSON
if [ -f "$DAEMON_JSON" ]; then
    CURRENT_CONFIG=$(cat "$DAEMON_JSON")
else
    CURRENT_CONFIG="{}"
fi

# 2. Use Python to add/update insecure-registries list safely
NEW_CONFIG=$(python3 -c "
import json, sys
try:
    config = json.loads(sys.argv[1])
except:
    config = {}
url = sys.argv[2]
registries = config.get('insecure-registries', [])
if url not in registries:
    registries.append(url)
config['insecure-registries'] = registries
print(json.dumps(config, indent=2))
" "$CURRENT_CONFIG" "$REGISTRY_URL")

echo "Writing new config to $DAEMON_JSON..."
echo "$NEW_CONFIG" | sudo tee "$DAEMON_JSON" > /dev/null

# 3. Restart Docker to apply changes
echo "Restarting Docker..."
sudo systemctl restart docker

echo "Docker configured and restarted successfully."
