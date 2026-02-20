#!/bin/bash
set -e

# Configuration
NVIM_FORK_URL="https://github.com/InTEGr8or/nvim.git"
LOCAL_BIN_DIR="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN_DIR"

# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$LOCAL_BIN_DIR:"* ]]; then
    echo "Adding $LOCAL_BIN_DIR to PATH in .bashrc"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install mise
if ! command -v mise &> /dev/null; then
    echo "Installing mise..."
    curl https://mise.jdx.dev/install.sh | sh
    # mise install script usually adds to ~/.local/bin/mise
else
    echo "mise already installed."
fi

# Install zoxide
if ! command -v zoxide &> /dev/null; then
    echo "Installing zoxide..."
    curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh -s -- --bin-dir "$LOCAL_BIN_DIR"
else
    echo "zoxide already installed."
fi

# Setup shell integration in .bashrc
if ! grep -q "mise activate bash" ~/.bashrc; then
    echo "Adding mise activation to .bashrc"
    echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
fi

if ! grep -q "zoxide init bash" ~/.bashrc; then
    echo "Adding zoxide initialization to .bashrc"
    echo 'eval "$(zoxide init bash)"' >> ~/.bashrc
fi

# Setup NVim Kickstarter fork
NVIM_CONFIG_DIR="$HOME/.config/nvim"
if [ -d "$NVIM_CONFIG_DIR" ]; then
    if [ -d "$NVIM_CONFIG_DIR/.git" ]; then
        REMOTE_URL=$(git -C "$NVIM_CONFIG_DIR" remote get-url origin 2>/dev/null || echo "")
        if [[ "$REMOTE_URL" != *"$NVIM_FORK_URL"* ]]; then
            echo "Backing up existing nvim config and cloning fork..."
            mv "$NVIM_CONFIG_DIR" "${NVIM_CONFIG_DIR}.bak.$(date +%Y%m%d%H%M%S)"
            git clone "$NVIM_FORK_URL" "$NVIM_CONFIG_DIR"
        else
            echo "nvim fork already cloned. Updating..."
            git -C "$NVIM_CONFIG_DIR" pull
        fi
    else
        echo "Backing up existing non-git nvim config and cloning fork..."
        mv "$NVIM_CONFIG_DIR" "${NVIM_CONFIG_DIR}.bak.$(date +%Y%m%d%H%M%S)"
        git clone "$NVIM_FORK_URL" "$NVIM_CONFIG_DIR"
    fi
else
    echo "Cloning nvim fork..."
    mkdir -p "$HOME/.config"
    git clone "$NVIM_FORK_URL" "$NVIM_CONFIG_DIR"
fi

echo "Tools installation complete on $(hostname)!"
