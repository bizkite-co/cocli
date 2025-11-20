#!/usr/bin/env python3
import os
import subprocess
import sys
import argparse
from datetime import datetime

# Removed LOCAL_FILE_PATH, CONTAINER_FILE_PATH, TEMP_DIR as mtime comparison is being removed.

def find_running_container(image_name: str) -> str | None:
    """Find a running container ID by image name."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"ancestor={image_name}", "--format", "{{.ID}}"],
            check=True,
            capture_output=True
        )
        container_ids = result.stdout.decode().strip().split('\n')
        if container_ids and container_ids[0]:
            return container_ids[0]
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error finding running container: {e.stderr.decode()}", file=sys.stderr)
        return None

def main() -> None:
    parser = argparse.ArgumentParser(description="Check if the Docker enrichment service container is running.")
    parser.add_argument("--image-name", required=True, help="Name of the Docker image (e.g., enrichment-service).")
    args = parser.parse_args()

    print(f"Searching for running container with image '{args.image_name}'...")
    container_id = find_running_container(args.image_name)
    if not container_id:
        print(f"No running container found for image '{args.image_name}'.", file=sys.stderr)
        sys.exit(1)
    print(f"Found running container: {container_id}")
    sys.exit(0) # Indicate that a container is running

if __name__ == "__main__":
    main()
