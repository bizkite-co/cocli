#!/usr/bin/env python3
import os
import subprocess
import sys
import argparse
from datetime import datetime

LOCAL_FILE_PATH = "cocli/enrichment/website_scraper.py"
CONTAINER_FILE_PATH = "/app/cocli/enrichment/website_scraper.py"
TEMP_DIR = "/tmp/cocli_comparison"

def get_file_mtime(filepath: str) -> float | None:
    """Get the modification time of a local file."""
    try:
        return os.path.getmtime(filepath)
    except FileNotFoundError:
        return None

def get_container_file_mtime(container_id: str) -> str | None:
    """Copy file from container and get its modification time."""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    temp_container_file = os.path.join(TEMP_DIR, os.path.basename(LOCAL_FILE_PATH))
    
    try:
        # Copy file from container
        subprocess.run(
            ["docker", "cp", f"{container_id}:{CONTAINER_FILE_PATH}", temp_container_file],
            check=True,
            capture_output=True
        )
        return str(os.path.getmtime(temp_container_file))
    except subprocess.CalledProcessError as e:
        print(f"Error copying file from container: {e.stderr.decode()}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"File not found in container: {CONTAINER_FILE_PATH}", file=sys.stderr)
        return None
    finally:
        # Clean up the copied file
        if os.path.exists(temp_container_file):
            os.remove(temp_container_file)

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
    parser = argparse.ArgumentParser(description="Check if local website_scraper.py is newer than in Docker image.")
    parser.add_argument("--image-name", required=True, help="Name of the Docker image (e.g., enrichment-service).")
    parser.add_argument("--container-id", help="Optional: ID of the running Docker container.")
    args = parser.parse_args()

    local_mtime_raw = get_file_mtime(LOCAL_FILE_PATH)
    if local_mtime_raw is None:
        print(f"Error: Local file not found at {LOCAL_FILE_PATH}", file=sys.stderr)
        sys.exit(1)
    local_mtime = int(local_mtime_raw)

    print(f"Local website_scraper.py modification time: {datetime.fromtimestamp(local_mtime)}")

    container_id = args.container_id
    if not container_id:
        print(f"Searching for running container with image '{args.image_name}'...")
        container_id = find_running_container(args.image_name)
        if not container_id:
            print(f"No running container found for image '{args.image_name}'. Please ensure the container is running.", file=sys.stderr)
            sys.exit(1)
        print(f"Found running container: {container_id}")

    container_mtime_raw = get_container_file_mtime(container_id)
    if container_mtime_raw is None:
        print("Could not retrieve file from container. Exiting.", file=sys.stderr)
        sys.exit(1)
    container_mtime = int(container_mtime_raw)

    print(f"Container website_scraper.py modification time: {datetime.fromtimestamp(container_mtime)}")

    if local_mtime > container_mtime:
        print("Result: Local website_scraper.py is NEWER than in the Docker container.")
        sys.exit(1) # Indicate that local is newer
    else:
        print("Result: Local website_scraper.py is NOT newer than in the Docker container.")
        sys.exit(0) # Indicate that local is not newer

if __name__ == "__main__":
    main()
