import argparse
import json
import subprocess
import os
import sys

# Ensure cocli can be imported by adding the project root to sys.path
# This assumes the script is run from the project root or .venv/bin/cocli is available
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try to import cocli config, fallback if not in venv or path is wrong
try:
    from cocli.core.config import get_enrichment_service_url
except ImportError:
def get_service_url() -> str:
    """Get the enrichment service URL from environment."""
    return os.environ.get("COCLI_ENRICHMENT_SERVICE_URL", "http://localhost:8000")


def main() -> None: # Added return type annotation
    parser = argparse.ArgumentParser(description="Enrich a single domain using the Fargate service.")
    parser.add_argument("domain", help="The domain to enrich (e.g., example.com).")
    parser.add_argument("--navigation-timeout", type=int, default=None,
                        help="Optional: Timeout in milliseconds for Playwright navigation (e.g., 30000).")
    parser.add_argument("--force", action="store_true", help="Force re-enrichment.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for the enrichment service.")

    args = parser.parse_args()

    # Construct the payload
    payload = {
        "domain": args.domain,
        "force": args.force,
        "debug": args.debug,
    }
    if args.navigation_timeout is not None:
        payload["navigation_timeout_ms"] = args.navigation_timeout

    # Get the enrichment service URL
    enrichment_service_url = get_enrichment_service_url()
    enrich_url = f"{enrichment_service_url}/enrich"

    # Construct the curl command
    curl_command = [
        "curl",
        "-X", "POST",
        enrich_url,
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload)
    ]

    print(f"Enriching {args.domain} with payload: {json.dumps(payload)}")
    print(f"Executing: {' '.join(curl_command)}")

    # Execute the curl command
    subprocess.run(curl_command)

if __name__ == "__main__":
    main()
