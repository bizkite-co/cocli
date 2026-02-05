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

FILES_TO_PATCH: List[str] = [
    "cocli/core/paths.py",
    "cocli/core/config.py",
    "cocli/core/s3_company_manager.py",
    "cocli/core/domain_index_manager.py",
    "cocli/core/queue/filesystem.py",
    "cocli/core/queue/factory.py",
    "cocli/core/queue/command_sqs_queue.py",
    "cocli/core/reporting.py",
    "cocli/core/exclusions.py",
    "cocli/application/campaign_service.py",
    "cocli/commands/worker.py",
    "cocli/commands/smart_sync.py",
    "cocli/commands/exclude.py",
    "cocli/commands/__init__.py",
    "cocli/utils/smart_sync_up.py",
    "cocli/models/command.py",
]

REMOTE_TMP_DIR = "/tmp/cocli_hotfix"

def run_ssh(user: str, host: str, command: str) -> subprocess.CompletedProcess[str]:
    cmd = f"ssh {user}@{host} \"{command}\""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def deploy_to_host(user: str, host: str) -> None:
    console.print(f"\n[bold blue]Deploying hotfix to {host}...[/bold blue]")
    
    # 1. Create remote temp dir on HOST
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/application")
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/core/queue")
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/commands")
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/utils")
    run_ssh(user, host, f"mkdir -p {REMOTE_TMP_DIR}/cocli/models")

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
        
        # Ensure directories exist in container
        run_ssh(user, host, f"docker exec {container} mkdir -p /app/cocli/application /app/cocli/core/queue /app/cocli/commands /app/cocli/utils /app/cocli/models")
        run_ssh(user, host, f"docker exec {container} mkdir -p /usr/local/lib/python3.12/dist-packages/cocli/application /usr/local/lib/python3.12/dist-packages/cocli/core/queue /usr/local/lib/python3.12/dist-packages/cocli/commands /usr/local/lib/python3.12/dist-packages/cocli/utils /usr/local/lib/python3.12/dist-packages/cocli/models")

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
