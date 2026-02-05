import subprocess
import logging
from typing import Dict
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

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