#!/bin/bash
# High-Efficiency Provisioning Script for cocli Cluster Nodes
set -e

# Configuration
NVIM_FORK_URL="https://github.com/InTEGr8or/nvim.git"
LOCAL_BIN_DIR="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN_DIR"
mkdir -p "$HOME/.cocli/iot"

# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$LOCAL_BIN_DIR:"* ]]; then
    echo "Adding $LOCAL_BIN_DIR to PATH in .bashrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    export PATH="$HOME/.local/bin:$PATH"
fi

# 1. Update System & Core Tools
echo "Updating system and installing base dependencies..."
sudo apt-get update
sudo apt-get install -y git curl wget jq python3-pip python-is-python3 ca-certificates gnupg lsb-release

# 2. Install Docker (Official Convenience Script)
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    # Add user to docker group
    sudo usermod -aG docker "$USER"
    echo "Docker installed. Note: Group changes require log-out or 'newgrp docker'."
else
    echo "Docker already installed."
fi

# 2b. Configure Insecure Registry (for Cluster Hub)
HUB_REGISTRY="10.0.0.17:5000"
echo "Configuring insecure registry $HUB_REGISTRY..."
sudo mkdir -p /etc/docker
# Use jq to merge or create if it doesn't exist
if [ -f /etc/docker/daemon.json ]; then
    sudo jq ". + {\"insecure-registries\": (.\"insecure-registries\" // []) + [\"$HUB_REGISTRY\"] | unique}" /etc/docker/daemon.json | sudo tee /etc/docker/daemon.json.tmp
    sudo mv /etc/docker/daemon.json.tmp /etc/docker/daemon.json
else
    echo "{\"insecure-registries\": [\"$HUB_REGISTRY\"]}" | sudo tee /etc/docker/daemon.json
fi
sudo systemctl restart docker || true

# 3. Install uv (Fast Python Package Manager)
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "uv already installed."
fi

# 4. Install mise (Runtime Manager)
if ! command -v mise &> /dev/null; then
    echo "Installing mise..."
    curl https://mise.jdx.dev/install.sh | sh
    eval "$(~/.local/bin/mise activate bash)"
else
    echo "mise already installed."
fi

# 5. Install NeoVim & Core Tools via mise
echo "Installing NeoVim and dependencies via mise..."
~/.local/bin/mise use --global neovim@latest
~/.local/bin/mise use --global usage@latest

# 6. Install zoxide (Better cd)
if ! command -v zoxide &> /dev/null; then
    echo "Installing zoxide..."
    curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh -s -- --bin-dir "$LOCAL_BIN_DIR"
else
    echo "zoxide already installed."
fi

# Shell Integration Setup
if ! grep -q "mise activate bash" ~/.bashrc; then
    echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
fi

if ! grep -q "zoxide init bash" ~/.bashrc; then
    echo 'eval "$(zoxide init bash)"' >> ~/.bashrc
fi

# 7. Setup NVim Kickstarter fork (Configuration)
NVIM_CONFIG_DIR="$HOME/.config/nvim"
if [ ! -d "$NVIM_CONFIG_DIR" ]; then
    echo "Cloning nvim fork..."
    mkdir -p "$HOME/.config"
    git clone "$NVIM_FORK_URL" "$NVIM_CONFIG_DIR"
else
    echo "Updating existing nvim fork..."
    git -C "$NVIM_CONFIG_DIR" pull || true
fi

echo "Provisioning complete on $(hostname)!"
echo "IMPORTANT: Please log out and back in (or run 'newgrp docker') to use Docker without sudo."
