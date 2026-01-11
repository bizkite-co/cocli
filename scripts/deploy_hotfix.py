import subprocess
from rich.console import Console
from typing import List, Tuple

console = Console()

HOSTS: List[Tuple[str, str]] = [
    ("mstouffer", "cocli5x0.local"),
]

FILES_TO_PATCH: List[str] = [
    "cocli/core/paths.py",
    "cocli/core/config.py",
    "cocli/core/s3_company_manager.py",
    "cocli/core/s3_domain_manager.py",
    "cocli/core/queue/filesystem.py",
    "cocli/core/reporting.py",
    "cocli/commands/worker.py",
    "cocli/utils/smart_sync_up.py",
]

REMOTE_TMP_DIR = "/tmp/cocli_hotfix"

def run_ssh(user: str, host: str, command: str) -> subprocess.CompletedProcess[str]:
    cmd = f"ssh {user}@{host} \"{command}\""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def deploy_to_host(user: str, host: str) -> None:
    console.print(f"\n[bold blue]Deploying hotfix to {host}...[/bold blue]")
    
    # 1. Create remote temp dir
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/core/queue")
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/commands")
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/utils")

    # 2. SCP files
    for file_path in FILES_TO_PATCH:
        remote_path = f"{REMOTE_TMP_DIR}/{file_path}"
        cmd = f"scp {file_path} {user}@{host}:{remote_path}"
        console.print(f"  Copying {file_path} to host...")
        subprocess.run(cmd, shell=True, check=True)

    # 3. Find running cocli containers
    res = run_ssh(user, host, "docker ps --format '{{.Names}}' | grep cocli")
    containers = [c for c in res.stdout.splitlines() if c.strip()]
    
    for container in containers:
        console.print(f"  Patching container: [cyan]{container}[/cyan]")
        for file_path in FILES_TO_PATCH:
            remote_src = f"{REMOTE_TMP_DIR}/{file_path}"
            
            # Try both common locations
            dests = [
                f"/app/{file_path}",
                f"/usr/local/lib/python3.12/dist-packages/{file_path}"
            ]
            
            for dest in dests:
                # Direct copy, ignore errors if path doesn't exist
                cmd = f"docker cp {remote_src} {container}:{dest}"
                run_ssh(user, host, cmd)
        
        console.print(f"  Restarting {container}...")
        run_ssh(user, host, f"docker restart {container}")

    console.print(f"  [green]Host {host} updated.[/green]")

def main() -> None: 
    for user, host in HOSTS:
        deploy_to_host(user, host)

if __name__ == "__main__":
    main()
