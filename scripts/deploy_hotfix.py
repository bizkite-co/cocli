#!/usr/bin/env python3
import subprocess
from rich.console import Console
from typing import List, Tuple

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
    rsync_cmd = f"rsync -avz --delete cocli/ {user}@{host}:{REMOTE_TMP_DIR}/cocli/"
    console.print("  Syncing cocli/ package...")
    res = subprocess.run(rsync_cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        console.print(f"  [red]Rsync failed: {res.stderr}[/red]")
        return

    # 2. Find all cocli containers (including stopped ones)
    res = run_ssh(user, host, "docker ps -a --format '{{.Names}}' | grep cocli")
    containers = [c for c in res.stdout.splitlines() if c.strip()]
    
    for container in containers:
        # Check if container is running
        status_res = run_ssh(user, host, f"docker inspect -f '{{{{.State.Running}}}}' {container}")
        is_running = status_res.stdout.strip() == "true"
        
        if not is_running:
            console.print(f"  Starting stopped container: [cyan]{container}[/cyan]")
            run_ssh(user, host, f"docker start {container}")
            # Give it a second to initialize
            time.sleep(1)

        console.print(f"  Patching container: [cyan]{container}[/cyan]")
        
        # 1. Dynamically find the cocli installation path
        res = run_ssh(user, host, f"docker exec {container} python3 -c 'import cocli; print(cocli.__path__[0])'")
        if res.returncode != 0:
            console.print(f"  [red]Could not find cocli path in {container}: {res.stderr}[/red]")
            continue
            
        lib_path = res.stdout.strip()
        app_path = "/app/hotfix_cocli"
        
        # 2. Ensure /app/hotfix_cocli directory exists inside container
        run_ssh(user, host, f"docker exec {container} mkdir -p {app_path}")
        
        # 3. Copy code to /app/hotfix_cocli
        cmd = f"docker cp {REMOTE_TMP_DIR}/cocli/. {container}:{app_path}/"
        run_ssh(user, host, cmd)
        
        # 4. Use a bind-mount style replacement or direct overwrite if symlink is risky
        # Direct overwrite is safer for site-packages if we want to be sure
        console.print(f"  Overwriting {lib_path} with hotfixed code...")
        run_ssh(user, host, f"docker exec {container} cp -r {app_path}/. {lib_path}/")

        console.print(f"  Restarting {container}...")
        run_ssh(user, host, f"docker restart {container}")
        
        # 5. Verify the patch (check for a recent change, e.g., the presence of UNIT_SEP in utils)
        verify_res = run_ssh(user, host, f"docker exec {container} grep 'UNIT_SEP =' {lib_path}/core/utils.py")
        if verify_res.returncode == 0:
            console.print(f"  [green]Verification PASSED for {container}[/green]")
        else:
            console.print(f"  [red]Verification FAILED for {container}[/red]")

    console.print(f"  [green]Host {host} updated successfully.[/green]")

def main() -> None: 
    for user, host in HOSTS:
        try:
            deploy_to_host(user, host)
        except Exception as e:
            console.print(f"[red]Error on {host}: {e}[/red]")

if __name__ == "__main__":
    main()