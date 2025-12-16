#!/bin/bash
set -e

# Update and install dependencies
echo "Updating system and installing dependencies..."
sudo apt-get update
sudo apt-get install -y git

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

# Create repos directory
mkdir -p ~/repos

# Clone or update repo
if [ -d "~/repos/cocli" ]; then
    echo "Updating cocli repo..."
    cd ~/repos/cocli
    git pull
else
    echo "Cloning cocli repo..."
    cd ~/repos
    git clone https://github.com/bizkite-co/cocli.git
fi

echo "Setup complete!"
