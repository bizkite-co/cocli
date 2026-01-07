import boto3
import subprocess
import logging
from pathlib import Path
from rich.console import Console
import configparser
import tempfile

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
            access_key = frozen_creds.access_key or ""
            secret_key = frozen_creds.secret_key or ""
            for section in ["default", profile_name]:
                creds_config[section] = {
                    "aws_access_key_id": access_key,
                    "aws_secret_access_key": secret_key,
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

def stop_rpi_workers(host: str, user: str = "mstouffer") -> None:
    """Stops and removes all cocli-related containers on the host."""
    cmd = "if [ -n \"$(docker ps -q --filter name=cocli-)\" ]; then docker stop $(docker ps -q --filter name=cocli-); fi; if [ -n \"$(docker ps -a -q --filter name=cocli-)\" ]; then docker rm $(docker ps -a -q --filter name=cocli-); fi"
    try:
        subprocess.run(["ssh", f"{user}@{host}", cmd], check=True, capture_output=True)
        console.print(f"[dim]Stopped all workers on {host}[/dim]")
    except Exception as e:
        logger.warning(f"Error stopping workers on {host}: {e}")

def start_rpi_worker(
    host: str, 
    campaign_name: str, 
    role: str, 
    profile: str,
    queues: Dict[str, str],
    user: str = "mstouffer",
    workers: int = 1
) -> bool:
    """Starts a specific worker role on the RPi."""
    container_name = f"cocli-{role}-worker"
    
    # Base command
    docker_cmd = [
        "docker", "run", "-d", "--restart", "always",
        "--name", container_name,
        "-e", "TZ=America/Los_Angeles",
        "-e", f"CAMPAIGN_NAME={campaign_name}",
        "-e", f"AWS_PROFILE={profile}",
        "-v", "~/.aws:/root/.aws:ro"
    ]

    # Add SQS URLs
    for env_var, url in queues.items():
        docker_cmd.extend(["-e", f"{env_var}={url}"])

    # Image and Command
    image = "cocli-worker-rpi:latest"
    if role == "details":
        docker_cmd.extend([image, "cocli", "worker", "details", "--workers", str(workers)])
    else:
        docker_cmd.append(image) # Default is 'scrape'

    full_cmd = " ".join(docker_cmd)
    
    try:
        console.print(f"[dim]Starting {role} worker on {host} ({workers} concurrent)...[/dim]")
        subprocess.run(["ssh", f"{user}@{host}", full_cmd], check=True, capture_output=True)
        console.print(f"[bold green]✓[/bold green] {role.capitalize()} worker started on {host}")
        return True
    except Exception as e:
        console.print(f"[bold red]Failed to start {role} worker on {host}:[/bold red] {e}")
        return False
