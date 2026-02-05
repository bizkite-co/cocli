import subprocess
import tomli
from pathlib import Path
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_ssh(host: str, command: str) -> str:
    logger.info(f"[{host}] Executing: {command}")
    result = subprocess.run(
        ["ssh", f"mstouffer@{host}", f"bash -c '{command}'"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        logger.error(f"[{host}] FAILED: {result.stderr}")
    return result.stdout.strip()

def main() -> None:
    config_path = Path.home() / ".config" / "cocli" / "cocli_config.toml"
    if not config_path.exists():
        logger.error("Cluster config not found.")
        sys.exit(1)

    with open(config_path, "rb") as f:
        config = tomli.load(f)

    nodes = config.get("cluster", {}).get("nodes", {})

    # The command sequence to update and reset the index
    update_cmd = """
    cd ~/repos/cocli && \
    git pull && \
    source .venv/bin/activate && \
    pip install duckdb && \
    rm -f ~/repos/data/indexes/*.csv && \
    export COCLI_DATA_HOME=~/repos/data && \
    python3 -c \"from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager; manager = WebsiteDomainCsvManager(); manager.rebuild_cache()\" && \
    echo \"Update Success\"
    """

    for hostname in nodes.keys():
        local_host = f"{hostname}.pi"
        logger.info(f"=== Updating Node: {hostname} ===")
        output = run_ssh(local_host, update_cmd)
        logger.info(f"[{hostname}] Result: {output}")

if __name__ == "__main__":
    main()
