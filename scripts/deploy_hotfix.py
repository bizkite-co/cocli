#!/usr/bin/env python3
import subprocess
import os
import sys
from rich.console import Console

console = Console()

REMOTE_TMP_DIR = "/tmp/cocli_hotfix"

def run_ssh(user: str, host: str, command: str) -> subprocess.CompletedProcess[str]:
    # Use a list for safer execution and avoid manual escaping where possible
    full_cmd = ["ssh", f"{user}@{host}", command]
    return subprocess.run(full_cmd, capture_output=True, text=True)

def deploy_to_host(user: str, host: str) -> bool:
    console.print(f"\n[bold blue]Deploying hotfix to {host} using RSYNC...[/bold blue]")
    
    # Ensure remote tmp dir exists
    subprocess.run(["ssh", f"{user}@{host}", f"mkdir -p {REMOTE_TMP_DIR}"], capture_output=True)

    # 1. Sync the entire cocli directory, pyproject.toml, VERSION, Makefile, and mk/ to the host's temp dir
    rsync_cmd = f"rsync -avz --delete cocli pyproject.toml VERSION Makefile mk {user}@{host}:{REMOTE_TMP_DIR}/"
    console.print("  Syncing package files to temp...")
    res = subprocess.run(rsync_cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        console.print(f"  [red]Rsync failed: {res.stderr}[/red]")
        return False

    # 1.1 Also sync the Makefile and mk/ directly to the repo dir for CLI use
    repo_dir = "repos/cocli"
    rsync_repo_cmd = f"rsync -avz Makefile mk {user}@{host}:{repo_dir}/"
    console.print(f"  Updating remote repository at {repo_dir}...")
    subprocess.run(rsync_repo_cmd, shell=True, capture_output=True)

    # 2. Find all cocli containers
    res = run_ssh(user, host, "docker ps -a --format '{{.Names}}' | grep cocli")
    containers = [c for c in res.stdout.splitlines() if c.strip()]
    
    success = True
    for container in containers:
        console.print(f"  Patching container: [cyan]{container}[/cyan]")
        
        # 3. Create /app/hotfix directory inside container
        app_path = "/app/hotfix"
        run_ssh(user, host, f"docker exec {container} mkdir -p {app_path}")
        
        # 4. Copy everything to /app/hotfix (this puts cocli/ inside /app/hotfix/)
        cmd = f"docker cp {REMOTE_TMP_DIR}/. {container}:{app_path}/"
        run_ssh(user, host, cmd)
        
        # 5. Install dependencies
        console.print(f"  Installing dependencies in {container}...")
        run_ssh(user, host, f"docker exec {container} uv pip install zeroconf watchdog psutil --system")
        
        # 6. Resolve actual installation path and force overwrite
        res = run_ssh(user, host, f"docker exec {container} python3 -c 'import cocli; print(cocli.__path__[0])'")
        if res.returncode == 0:
            lib_path = res.stdout.strip()
            # If lib_path is /app/cocli, we want to replace it with /app/hotfix/cocli
            console.print(f"  Force-overwriting {lib_path}...")
            # We remove the existing one and copy the hotfixed one in its place
            run_ssh(user, host, f"docker exec {container} rm -rf {lib_path}")
            # If lib_path was /app/cocli, we copy /app/hotfix/cocli to /app/
            lib_parent = os.path.dirname(lib_path)
            run_ssh(user, host, f"docker exec {container} cp -r {app_path}/cocli {lib_parent}/")
        
        console.print(f"  Restarting {container}...")
        run_ssh(user, host, f"docker restart {container}")
        
        # 6. Final Verification: Use a simpler command to avoid quoting hell
        verify_cmd = f"docker exec {container} python3 -c \"import cocli.core.constants as c; print('UNIT_SEP=' + repr(c.UNIT_SEP))\""
        verify_res = run_ssh(user, host, verify_cmd)
        
        if verify_res.returncode == 0 and "UNIT_SEP=" in verify_res.stdout:
            console.print(f"  [green]Verification PASSED for {container}: {verify_res.stdout.strip()}[/green]")
        else:
            console.print(f"  [red]Verification FAILED for {container}[/red]")
            console.print(f"  Stdout: {verify_res.stdout}")
            console.print(f"  Stderr: {verify_res.stderr}")
            success = False

    return success

def main() -> None: 
    from cocli.core.config import get_campaign, load_campaign_config
    
    # Allow command line host override
    target_arg = sys.argv[1] if len(sys.argv) > 1 else None
    
    if target_arg and target_arg != "--children":
        deploy_to_host("mstouffer", target_arg)
        return

    campaign_name = get_campaign() or "roadmap"
    config = load_campaign_config(campaign_name)
    
    # 1. Try campaign config first
    cluster_config = config.get("cluster", {})
    nodes = cluster_config.get("nodes", [])

    # 2. Fallback to global config
    if not nodes:
        from cocli.core.paths import paths
        global_config_path = paths.root / "config" / "cocli_config.toml"
        if global_config_path.exists():
            import toml
            global_config = toml.load(global_config_path)
            nodes = global_config.get("cluster", {}).get("nodes", [])

    if not nodes:
        console.print("[yellow]No worker nodes configured for this campaign.[/yellow]")
        return

    for node in nodes:
        host = node["host"]
        user = "mstouffer"
        
        # Logic for staged deployment
        is_hub = host == "cocli5x1.pi"
        
        if target_arg == "--children":
            if is_hub:
                continue
        else:
            # Legacy default: all nodes
            pass
            
        try:
            deploy_to_host(user, host)
        except Exception as e:
            console.print(f"[red]Error on {host}: {e}[/red]")

if __name__ == "__main__":
    main()
