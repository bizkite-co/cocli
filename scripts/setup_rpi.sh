#!/bin/bash
set -e

# Update and install dependencies
echo "Updating system and installing dependencies..."
sudo apt-get update
sudo apt-get install -y git

# Join the tailnet, tagged as tag:cocli-worker. That tag is what the
# tailnet's ACL grants non-interactive ("accept", not "check") SSH between
# worker nodes - cocli/core/compact.py::isolate_wal() depends on it to pull
# a peer node's WAL during compaction with no SSH key ever provisioned.
# --ssh enables Tailscale SSH itself so this node can also be the target of
# that same rsync-over-ssh call from another worker.
if ! command -v tailscale &> /dev/null; then
    echo "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if [ -z "$TS_AUTHKEY" ]; then
    echo "Error: TS_AUTHKEY is required (a reusable Tailscale auth key scoped to tag:cocli-worker)." >&2
    echo "Generate one at https://login.tailscale.com/admin/settings/keys and re-run:" >&2
    echo "  TS_AUTHKEY=tskey-... make setup-rpi RPI_HOST=..." >&2
    exit 1
fi

echo "Joining tailnet as tag:cocli-worker..."
sudo tailscale up --authkey="$TS_AUTHKEY" --advertise-tags=tag:cocli-worker --ssh

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "Docker installed. Please log out and back in for group changes to take effect."
else
    echo "Docker already installed."
fi

# Create repos and data directory
# The data directory is critical as it is bind-mounted by the worker containers
mkdir -p ~/repos
mkdir -p ~/repos/data

# Clone or update repo
if [ -d "$HOME/repos/cocli" ]; then
    echo "Updating cocli repo..."
    cd ~/repos/cocli
    git pull
else
    echo "Cloning cocli repo..."
    cd ~/repos
    git clone https://github.com/bizkite-co/cocli.git
    cd ~/repos/cocli
fi

# Run high-efficiency tool provisioning
echo "Running tool provisioning..."
if [ -f "$HOME/provision_pi_tools.sh" ]; then
    bash "$HOME/provision_pi_tools.sh"
else
    bash scripts/provision_pi_tools.sh
fi

echo "Setup complete!"