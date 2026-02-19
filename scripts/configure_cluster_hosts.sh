#!/bin/bash
# Update /etc/hosts on a remote node with the cluster map.
# Usage: ./configure_cluster_hosts.sh <remote_host> <json_host_map>

set -e

REMOTE_HOST=$1
HOST_MAP_JSON=$2
RPI_USER="mstouffer"

if [ -z "$REMOTE_HOST" ] || [ -z "$HOST_MAP_JSON" ]; then
    echo "Usage: $0 <remote_host> <json_host_map>"
    exit 1
fi

echo "Updating /etc/hosts on $REMOTE_HOST..."

# Create a small python script to perform the update
REMOTE_SCRIPT="/tmp/update_hosts.py"
LOCAL_SCRIPT="/tmp/local_update_hosts.py"

cat <<'EOF' > "$LOCAL_SCRIPT"
import json, sys, tempfile, os

host_map_json = sys.argv[1]
host_map = json.loads(host_map_json)
hosts_path = '/etc/hosts'

with open(hosts_path, 'r') as f:
    lines = f.readlines()

# Filter out any existing entries for our cluster nodes
new_lines = []
cluster_hosts = set(host_map.keys())
for line in lines:
    parts = line.split()
    if len(parts) >= 2 and parts[1] in cluster_hosts:
        continue
    new_lines.append(line)

# Add fresh entries
for host, ip in host_map.items():
    new_lines.append(f'{ip}\t{host}\n')

# Write to a temp file
fd, path = tempfile.mkstemp()
try:
    with os.fdopen(fd, 'w') as tmp:
        tmp.writelines(new_lines)
    # Use sudo to move into place
    os.system(f'sudo mv {path} {hosts_path}')
    os.system(f'sudo chmod 644 {hosts_path}')
finally:
    if os.path.exists(path):
        try: os.remove(path)
        except: pass
EOF

scp "$LOCAL_SCRIPT" "$RPI_USER@$REMOTE_HOST:$REMOTE_SCRIPT"
ssh "$RPI_USER@$REMOTE_HOST" "python3 $REMOTE_SCRIPT '$HOST_MAP_JSON' && rm $REMOTE_SCRIPT"
rm "$LOCAL_SCRIPT"

echo "Success: /etc/hosts updated on $REMOTE_HOST"
