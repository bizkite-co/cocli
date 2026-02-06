#!/usr/bin/env python3
import subprocess
from rich.console import Console
from typing import List, Tuple
import os

console = Console()

HOSTS: List[Tuple[str, str]] = [
    ("mstouffer", "octoprint.pi"),
    ("mstouffer", "coclipi.pi"),
    ("mstouffer", "cocli5x0.pi"),
    ("mstouffer", "cocli5x1.pi"),
]

REMOTE_TMP_DIR = "/tmp/cocli_hotfix"

def run_ssh(user: str, host: str, command: str) -> subprocess.CompletedProcess[str]:
    cmd = f"ssh {user}@{host} \"{command}\""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def deploy_to_host(user: str, host: str) -> None:
    console.print(f"\n[bold blue]Deploying hotfix to {host} using RSYNC...[/bold blue]")
    
    # 1. Sync the entire cocli directory to the host's temp dir
    # -a: archive mode (preserves permissions, recursive)
    # -z: compress
    # --delete: mirror exactly (remove files on remote that are gone locally)
    rsync_cmd = f"rsync -avz --delete cocli/ {user}@{host}:{REMOTE_TMP_DIR}/cocli/"
    console.print(f"  Syncing cocli/ package...")
    res = subprocess.run(rsync_cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        console.print(f"  [red]Rsync failed: {res.stderr}[/red]")
        return

    # 2. Find running cocli containers
    res = run_ssh(user, host, "docker ps --format '{{.Names}}' | grep cocli")
    containers = [c for c in res.stdout.splitlines() if c.strip()]
    
    for container in containers:
        console.print(f"  Patching container: [cyan]{container}[/cyan]")
        
        # Determine the site-packages path inside the container
        # We assume python 3.12 based on previous logs, but could be dynamic.
        lib_path = "/usr/local/lib/python3.12/dist-packages/cocli"
        
        # Use docker cp to update the entire package at once
        # Note: docker cp replaces the directory if it exists
        cmd = f"docker cp {REMOTE_TMP_DIR}/cocli/. {container}:{lib_path}/"
        run_ssh(user, host, cmd)
        
        # Also update /app mount if it exists (for dev-mode consistency)
        run_ssh(user, host, f"docker exec {container} [ -d /app/cocli ] && docker cp {REMOTE_TMP_DIR}/cocli/. {container}:/app/cocli/ || true")

        console.print(f"  Restarting {container}...")
        run_ssh(user, host, f"docker restart {container}")

    console.print(f"  [green]Host {host} updated successfully.[/green]")

def main() -> None: 
    for user, host in HOSTS:
        try:
            deploy_to_host(user, host)
        except Exception as e:
            console.print(f"[red]Error on {host}: {e}[/red]")

if __name__ == "__main__":
    main()
