import sys
import subprocess
import argparse
import logging
from pathlib import Path
from typing import List
from rich.console import Console
from rich.table import Table

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import load_campaign_config, get_campaign

console = Console()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def check_local(path: str) -> bool:
    return Path(path).exists()

def check_remote_pi(host: str, path: str) -> bool:
    try:
        # Check if directory exists and has files (silently)
        cmd = f"ls -d {path} >/dev/null 2>&1 && echo 'EXISTS' || echo 'MISSING'"
        res = subprocess.run(["ssh", f"mstouffer@{host}", cmd], capture_output=True, text=True, timeout=5)
        return "EXISTS" in res.stdout
    except Exception:
        return False

def check_s3(bucket: str, profile: str, path: str) -> bool:
    try:
        # S3 paths usually don't have leading slashes
        s3_path = path.lstrip("/")
        cmd = ["aws", "s3", "ls", f"s3://{bucket}/{s3_path}", "--profile", profile]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.returncode == 0 and len(res.stdout.strip()) > 0
    except Exception:
        return False

def audit_paths(campaigns: List[str], target_paths: List[str]) -> None:
    from cocli.core.paths import paths
    import tomli
    
    # Use the definitive path from our authority
    config_path = paths.root / "config" / "cocli_config.toml"
    global_config = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            global_config = tomli.load(f)
            
    nodes = global_config.get("cluster", {}).get("nodes", [])
    
    table = Table(title="Cluster Path Audit")
    table.add_column("Campaign", style="cyan")
    table.add_column("Path Template", style="magenta")
    table.add_column("Location", style="yellow")
    table.add_column("Status", justify="center")

    for campaign in campaigns:
        try:
            config = load_campaign_config(campaign)
            aws_config = config.get("aws", {})
            bucket = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name")
            profile = aws_config.get("profile") or aws_config.get("aws_profile", "default")
            
            # Local Root is always 'data/' symlink in this repo context
            local_root = Path("data")

            for template in target_paths:
                # Replace {campaign} placeholder
                actual_path = template.replace("{campaign}", campaign)
                
                # 1. Check Local
                local_path = local_root / actual_path.lstrip("/")
                exists = check_local(str(local_path))
                table.add_row(campaign, template, "Local", "[green]FOUND[/green]" if exists else "[red]MISSING[/red]")

                # 2. Check PIs
                for node in nodes:
                    host = node['host']
                    # PIs always use ~/.local/share/cocli_data/
                    pi_path = f"~/.local/share/cocli_data/{actual_path.lstrip('/')}"
                    exists = check_remote_pi(host, pi_path)
                    table.add_row(campaign, template, f"Pi: {host}", "[green]FOUND[/green]" if exists else "[red]MISSING[/red]")

                # 3. Check S3
                if bucket:
                    exists = check_s3(bucket, profile, actual_path)
                    table.add_row(campaign, template, f"S3: {bucket}", "[green]FOUND[/green]" if exists else "[red]MISSING[/red]")
                else:
                    table.add_row(campaign, template, "S3", "[yellow]NO BUCKET[/yellow]")

        except Exception as e:
            console.print(f"[red]Error auditing campaign {campaign}: {e}[/red]")

    console.print(table)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit specific paths across the cluster and S3.")
    parser.add_argument("--campaigns", help="Comma-separated list of campaigns to audit", default=get_campaign())
    parser.add_argument("--paths", help="Comma-separated list of path templates (use {campaign} placeholder)", required=True)
    
    args = parser.parse_args()
    
    campaign_list = [c.strip() for c in args.campaigns.split(",")]
    path_list = [p.strip() for p in args.paths.split(",")]
    
    audit_paths(campaign_list, path_list)
