import boto3
import subprocess
import logging
from pathlib import Path
from typing import Optional
from rich.console import Console
import configparser
import tempfile
import os

logger = logging.getLogger(__name__)
console = Console()

def deploy_rpi_credentials(profile_name: str, host: str, user: str = "mstouffer") -> bool:
    """
    Resolves AWS credentials for a profile using boto3 and deploys them to a Raspberry Pi.
    Handles SSO and standard credential files.
    """
    try:
        # 1. Resolve Credentials using boto3 (handles SSO, config, credentials, env)
        session = boto3.Session(profile_name=profile_name)
        creds = session.get_credentials()
        if not creds:
            console.print(f"[bold red]Error:[/bold red] Could not resolve credentials for profile '{profile_name}'.")
            return False
        
        frozen_creds = creds.get_frozen_credentials()
        region = session.region_name or "us-east-1"

        # 2. Prepare temporary credential files
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_creds_path = Path(tmp_dir) / "credentials"
            tmp_config_path = Path(tmp_dir) / "config"

            # Create [default] and [profile] sections for convenience
            creds_config = configparser.ConfigParser()
            for section in ["default", profile_name]:
                creds_config[section] = {
                    "aws_access_key_id": frozen_creds.access_key,
                    "aws_secret_access_key": frozen_creds.secret_key,
                }
                if frozen_creds.token:
                    creds_config[section]["aws_session_token"] = frozen_creds.token

            with open(tmp_creds_path, "w") as f:
                creds_config.write(f)

            # Create config file with region
            config_config = configparser.ConfigParser()
            for section in ["default", f"profile {profile_name}"]:
                config_config[section] = {
                    "region": region,
                    "output": "json"
                }
            with open(tmp_config_path, "w") as f:
                config_config.write(f)

            # 3. Deploy via SCP
            console.print(f"[dim]Deploying '{profile_name}' credentials to {user}@{host}...[/dim]")
            
            # Ensure .aws dir exists
            subprocess.run(["ssh", f"{user}@{host}", "mkdir -p ~/.aws"], check=True, capture_output=True)
            
            # Copy files
            subprocess.run(["scp", str(tmp_creds_path), f"{user}@{host}:~/.aws/credentials"], check=True, capture_output=True)
            subprocess.run(["scp", str(tmp_config_path), f"{user}@{host}:~/.aws/config"], check=True, capture_output=True)

            console.print(f"[bold green]✓[/bold green] Credentials for '{profile_name}' deployed to {host}")
            return True

    except Exception as e:
        console.print(f"[bold red]Failed to deploy credentials to {host}:[/bold red] {e}")
        return False
