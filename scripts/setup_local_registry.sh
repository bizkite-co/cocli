#!/bin/bash
# Setup a local Docker registry on the host.
# Usage: ./setup_local_registry.sh

set -e

REGISTRY_NAME="cocli-registry"
REGISTRY_PORT=5000
STORAGE_DIR="$HOME/docker-registry"

echo "Setting up local Docker registry..."

# 1. Create storage directory for persistent images
mkdir -p "$STORAGE_DIR"

# 2. Start the registry container
if docker ps -a --format '{{.Names}}' | grep -q "^${REGISTRY_NAME}$"; then
    echo "Registry container already exists. Restarting..."
    docker stop "$REGISTRY_NAME" || true
    docker rm "$REGISTRY_NAME" || true
fi

echo "Starting registry container on port $REGISTRY_PORT..."
docker run -d \
  --name "$REGISTRY_NAME" \
  --restart always \
  -p "$REGISTRY_PORT":5000 \
  -v "$STORAGE_DIR":/var/lib/registry \
  registry:2

echo "Local registry is now running on port $REGISTRY_PORT."
echo "Storage is persisted at: $STORAGE_DIR"
