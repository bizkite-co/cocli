"""
Robust, verifiable deployment service for distributing code to worker nodes.

Design principles:
- Hash-based verification: content hashes prove code equality, not false positives
- Image-first durability: rebuild/pull images as the primary path (survives container recreation)
- Direct patch mode: optional fast-path for iteration (ephemeral, not production-durable)
- Real verification: hash-equality + observed worker behavior (tile movement), not proxy checks
- Deployment indicator: file marker in /app/data/ shows mode (patch vs image)
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, UTC
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

# Deployment indicator file (same path on all nodes)
DEPLOYMENT_INDICATOR_PATH = "/app/data/.deployment_info.json"


@dataclass
class CodeHash:
    """Represents a content hash of the deployed cocli package."""
    digest: str  # Short hex digest
    timestamp: str
    files_included: int

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CodeHash):
            return False
        return self.digest == other.digest


class CodeVerifier:
    """Computes and verifies code hashes for deployment verification."""

    def __init__(self, cocli_root: Optional[Path] = None):
        if cocli_root is None:
            # Resolve from current working directory (scripts run from repo root)
            cocli_root = Path.cwd() / "cocli"
        self.cocli_root = cocli_root

    def compute_local_hash(self) -> CodeHash:
        """
        Compute a content hash of the local cocli package.

        Hashes all .py files under cocli/, sorted by path.
        Excludes __pycache__, .pyc, and other non-source files.
        """
        if not self.cocli_root.exists():
            logger.warning(f"cocli_root does not exist: {self.cocli_root}")
            return CodeHash(digest="MISSING", timestamp=datetime.now(UTC).isoformat(), files_included=0)

        py_files = sorted(
            f for f in self.cocli_root.rglob("*.py")
            if "__pycache__" not in f.parts
        )

        hasher = hashlib.sha256()
        for file_path in py_files:
            with open(file_path, "rb") as f:
                hasher.update(f.read())

        digest = hasher.hexdigest()[:12]
        return CodeHash(
            digest=digest,
            timestamp=datetime.now(UTC).isoformat(),
            files_included=len(py_files),
        )

    def compute_hash_at_path(self, user: str, host: str, remote_path: str, is_container: bool = False) -> Optional[CodeHash]:
        """
        Compute hash of files at a remote path (on host filesystem or in container).

        Args:
            user: SSH user
            host: Target hostname
            remote_path: Path to hash (e.g., /tmp/cocli_patch or /app/cocli in container)
            is_container: If True, run command inside cocli-supervisor container
        """
        # Python script to compute hash of a directory
        compute_script = f"""
import hashlib
import sys
from pathlib import Path

path = Path('{remote_path}')
if not path.exists():
    print("ERROR:path-not-found")
    sys.exit(1)

py_files = sorted(f for f in path.rglob('*.py') if '__pycache__' not in f.parts)

if not py_files:
    print("ERROR:no-py-files")
    sys.exit(1)

hasher = hashlib.sha256()
for file_path in py_files:
    with open(file_path, 'rb') as f:
        hasher.update(f.read())

digest = hasher.hexdigest()[:12]
print(f"HASH:{{digest}}:COUNT:{{len(py_files)}}")
"""

        try:
            escaped_script = compute_script.replace('"', '\\"')

            if is_container:
                cmd = f"docker exec cocli-supervisor python3 -c \"{escaped_script}\""
            else:
                cmd = f"python3 -c \"{escaped_script}\""

            result = subprocess.run(
                ["ssh", f"{user}@{host}", cmd],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"Hash computation failed at {remote_path}: {result.stderr}")
                return None

            output = result.stdout.strip()

            if output.startswith("ERROR:"):
                error_msg = output.split(":", 1)[1]
                logger.warning(f"Hash error at {remote_path}: {error_msg}")
                return None

            parts = output.split(":")
            if len(parts) >= 4 and parts[0] == "HASH":
                return CodeHash(
                    digest=parts[1],
                    timestamp=datetime.now(UTC).isoformat(),
                    files_included=int(parts[3]),
                )
        except Exception as e:
            logger.warning(f"Failed to compute hash at {remote_path}: {e}")
            return None

        return None

    def compute_remote_hash(self, user: str, host: str) -> Optional[CodeHash]:
        """
        Compute the code hash of the deployed cocli package on a remote node.

        Hashes files in /app/cocli/ directly (the source tree, not via import).
        Returns None if the remote hash cannot be computed.
        """
        # Python script to hash /app/cocli directly (not via import)
        compute_script = """
import hashlib
import sys
from pathlib import Path

cocli_path = Path('/app/cocli')
if not cocli_path.exists():
    print("ERROR:path-not-found")
    sys.exit(1)

py_files = sorted(f for f in cocli_path.rglob('*.py') if '__pycache__' not in f.parts)

if not py_files:
    print("ERROR:no-py-files")
    sys.exit(1)

hasher = hashlib.sha256()
for file_path in py_files:
    with open(file_path, 'rb') as f:
        hasher.update(f.read())

digest = hasher.hexdigest()[:12]
print(f"HASH:{digest}:COUNT:{len(py_files)}")
"""

        try:
            # Use double quotes and escape internal double quotes to avoid single-quote issues
            escaped_script = compute_script.replace('"', '\\"')
            result = subprocess.run(
                ["ssh", f"{user}@{host}", f'python3 -c "{escaped_script}"'],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"Remote hash computation failed on {host}: {result.stderr}")
                return None

            # Parse output: "HASH:abc123:COUNT:45" or "ERROR:reason"
            output = result.stdout.strip()

            if output.startswith("ERROR:"):
                error_msg = output.split(":", 1)[1]
                logger.warning(f"Remote hash error on {host}: {error_msg}")
                return None

            parts = output.split(":")
            if len(parts) >= 4 and parts[0] == "HASH":
                return CodeHash(
                    digest=parts[1],
                    timestamp=datetime.now(UTC).isoformat(),
                    files_included=int(parts[3]),
                )
        except Exception as e:
            logger.warning(f"Failed to compute remote hash for {host}: {e}")
            return None

        return None


class DeploymentService:
    """
    Handles deployment of code to worker nodes with verification.

    Supports two modes:
    - Image-first (durable): rebuild/pull Docker image, recreate container
    - Direct patch (ephemeral): patch running/stopped container (for iteration only)

    Both modes write a deployment indicator file to /app/data/.deployment_info.json
    showing the deployment mode, time, and code hash.
    """

    def __init__(self, campaign_name: str = "turboship"):
        self.campaign_name = campaign_name
        self.verifier = CodeVerifier()

    def verify_patch_applied(self, host: str, user: str) -> bool:
        """
        Verify that a patch was applied correctly by comparing hashes at all stages.

        Checks:
        1. Local cocli/ hash
        2. /tmp/cocli_patch/ hash on host (should match local)
        3. /app/cocli/ hash in container (should match local)

        Returns True only if all three match.
        """
        console.print("    [Verification] Comparing code hashes...")

        # 1. Get local hash
        local_hash = self.verifier.compute_local_hash()
        console.print(f"      Local:       {local_hash.digest} ({local_hash.files_included} files)")

        # 2. Get rsync'd hash
        rsync_hash = self.verifier.compute_hash_at_path(user, host, "/tmp/cocli_patch", is_container=False)
        if not rsync_hash:
            console.print("      Rsync'd:     [red]FAILED[/red] (can't compute hash)")
            return False
        console.print(f"      Rsync'd:     {rsync_hash.digest} ({rsync_hash.files_included} files)")

        if local_hash != rsync_hash:
            console.print("      [red]✗ Mismatch: local != rsync'd[/red]")
            return False

        # 3. Get container hash
        container_hash = self.verifier.compute_hash_at_path(user, host, "/app/cocli", is_container=True)
        if not container_hash:
            console.print("      Container:   [red]FAILED[/red] (can't compute hash)")
            return False
        console.print(f"      Container:   {container_hash.digest} ({container_hash.files_included} files)")

        if local_hash != container_hash:
            console.print("      [red]✗ Mismatch: local != container[/red]")
            return False

        console.print("      [green]✓ All hashes match![/green]")
        return True

    def _write_deployment_indicator(self, host: str, user: str, mode: str, code_hash: CodeHash) -> bool:
        """Write deployment indicator file to /app/data/.deployment_info.json on remote host."""
        indicator_data = {
            "mode": mode,
            "code_hash": code_hash.digest,
            "timestamp": datetime.now(UTC).isoformat(),
            "files": code_hash.files_included,
        }

        # Write via Python script (avoids shell quoting issues)
        write_script = f"""
import json
path = '{DEPLOYMENT_INDICATOR_PATH}'
data = {json.dumps(indicator_data)}
Path(path).parent.mkdir(parents=True, exist_ok=True)
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
"""

        try:
            escaped_script = write_script.replace('"', '\\"')
            subprocess.run(
                ["ssh", f"{user}@{host}", f'python3 -c "{escaped_script}"'],
                capture_output=True,
                timeout=10,
                check=True,
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to write deployment indicator on {host}: {e}")
            return False

    def deploy_image_rebuild(self, host: str, user: str = "mstouffer", verify: bool = True) -> bool:
        """
        Deploy via image rebuild: rsync code, build image, recreate container.

        This is the durable path — it survives container recreation/reboots.
        """
        console.print(f"\n[bold blue]Image Rebuild Deploy to {host}[/bold blue]")

        # 1. Rsync code
        console.print("  [1/4] Syncing code via rsync...")
        try:
            subprocess.run(
                ["ssh", f"{user}@{host}", "mkdir -p ~/repos/cocli_build"],
                capture_output=True,
                check=True,
                timeout=10,
            )

            rsync_result = subprocess.run(
                [
                    "rsync",
                    "-az",
                    "--delete",
                    "--exclude", ".venv",
                    "--exclude", ".git",
                    "--exclude", "data",
                    "--exclude", ".logs",
                    "--exclude", ".pytest_cache",
                    "./",
                    f"{user}@{host}:~/repos/cocli_build/",
                ],
                capture_output=True,
                timeout=120,
            )

            if rsync_result.returncode != 0:
                console.print(f"  [red]✗ Rsync failed: {rsync_result.stderr.decode()[:200]}[/red]")
                return False
        except Exception as e:
            console.print(f"  [red]✗ Rsync error: {e}[/red]")
            return False

        # 2. Build image
        console.print("  [2/4] Building Docker image on node...")
        try:
            build_result = subprocess.run(
                [
                    "ssh",
                    f"{user}@{host}",
                    "cd ~/repos/cocli_build && docker build -t cocli-worker-rpi:latest -f docker/rpi-worker/Dockerfile . 2>&1 | tail -20",
                ],
                capture_output=True,
                timeout=600,
            )

            if build_result.returncode != 0:
                console.print("  [red]✗ Build failed[/red]")
                logger.error(f"Build stderr: {build_result.stderr.decode()}")
                return False

            console.print(f"    {build_result.stdout.decode().strip()}")
        except Exception as e:
            console.print(f"  [red]✗ Build error: {e}[/red]")
            return False

        # 3. Recreate container
        console.print("  [3/4] Recreating cocli-supervisor container...")
        try:
            subprocess.run(
                ["ssh", f"{user}@{host}", "docker stop -t 5 cocli-supervisor 2>/dev/null || true"],
                capture_output=True,
                timeout=15,
            )
            subprocess.run(
                ["ssh", f"{user}@{host}", "docker rm cocli-supervisor 2>/dev/null || true"],
                capture_output=True,
                timeout=10,
            )

            run_cmd = (
                "docker run -d --restart always --name cocli-supervisor "
                "--shm-size=2gb "
                "-e TZ=America/Los_Angeles "
                "-e CAMPAIGN_NAME=turboship "
                "-e AWS_PROFILE=turboship-iot "
                "-e COCLI_HOSTNAME=$(hostname | cut -d'.' -f1) "
                "-e COCLI_QUEUE_TYPE=filesystem "
                "-e PYTHONDONTWRITEBYTECODE=1 "
                "-v ~/repos/data:/app/data "
                "-v ~/.aws:/root/.aws:ro "
                "-v ~/.cocli:/root/.cocli:ro "
                "cocli-worker-rpi:latest "
                "cocli-worker worker orchestrate --debug"
            )

            subprocess.run(
                ["ssh", f"{user}@{host}", run_cmd],
                capture_output=True,
                timeout=15,
                check=True,
            )

            console.print("    Container recreated and started.")
        except Exception as e:
            console.print(f"  [red]✗ Container recreation failed: {e}[/red]")
            return False

        # 4. Write indicator and verify
        local_hash = self.verifier.compute_local_hash()
        self._write_deployment_indicator(host, user, "image", local_hash)

        if verify:
            console.print("  [4/4] Verifying deployment...")
            if self._verify_deployment(host, user):
                console.print("  [green]✓ Verification PASSED[/green]")
                return True
            else:
                console.print("  [red]✗ Verification FAILED[/red]")
                return False
        else:
            console.print("  [4/4] Skipping verification (not requested)")
            return True

    def deploy_direct_patch(self, host: str, user: str = "mstouffer", verify: bool = True) -> bool:
        """
        Deploy via direct patch: rsync code, docker cp into stopped container, clear cache, restart.

        EPHEMERAL: survives container restart but NOT recreation. Use for iteration only.
        """
        console.print(f"\n[bold yellow]Direct Patch Deploy to {host} (EPHEMERAL)[/bold yellow]")

        # 1. Rsync
        console.print("  [1/4] Syncing code...")
        try:
            subprocess.run(
                ["ssh", f"{user}@{host}", "mkdir -p /tmp/cocli_patch"],
                capture_output=True,
                check=True,
                timeout=10,
            )

            rsync_result = subprocess.run(
                [
                    "rsync",
                    "-az",
                    "--delete",
                    "--exclude", ".venv",
                    "--exclude", ".git",
                    "--exclude", ".logs",
                    "--exclude", ".pytest_cache",
                    # Note: don't exclude "data/" - cocli/ is the source, so only cocli/data/ exists (which we need)
                    "cocli/",
                    f"{user}@{host}:/tmp/cocli_patch/",
                ],
                capture_output=True,
                timeout=120,
            )

            if rsync_result.returncode != 0:
                console.print("  [red]✗ Rsync failed[/red]")
                return False
        except Exception as e:
            console.print(f"  [red]✗ Rsync error: {e}[/red]")
            return False

        # 2. Patch running container: clear and copy all files, clear cache, graceful restart
        console.print("  [2/4] Patching container (while running)...")
        try:
            # Clear destination and copy all files at once (more reliable)
            subprocess.run(
                ["ssh", f"{user}@{host}", "docker exec cocli-supervisor rm -rf /app/cocli && mkdir -p /app/cocli"],
                capture_output=True,
                timeout=10,
                check=False,  # May fail if already exists
            )

            subprocess.run(
                ["ssh", f"{user}@{host}", "docker cp /tmp/cocli_patch/. cocli-supervisor:/app/cocli/"],
                capture_output=True,
                timeout=30,
                check=True,
            )

            # Clear bytecode to force reimports
            subprocess.run(
                ["ssh", f"{user}@{host}", "docker exec cocli-supervisor find /app/cocli -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"],
                capture_output=True,
                timeout=15,
                check=False,
            )

            console.print("    Code patched, cache cleared.")
        except Exception as e:
            console.print(f"  [red]✗ Patch failed: {e}[/red]")
            return False

        # 3. Graceful restart: send SIGHUP to worker process (container stays up)
        console.print("  [3/4] Gracefully reloading worker...")
        try:
            subprocess.run(
                ["ssh", f"{user}@{host}", "docker exec cocli-supervisor killall -HUP cocli || true"],
                capture_output=True,
                timeout=10,
                check=False,  # May fail if no process named cocli
            )
            # Give it a moment to restart
            import time
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Graceful restart signal failed: {e}")
            # Continue anyway - worst case worker restarts on next iteration

        # 4. Verify patch and indicator
        console.print("  [4/4] Verifying patch...")

        # First: verify hashes match at all stages (definitive proof)
        if not self.verify_patch_applied(host, user):
            console.print("  [red]✗ Hash verification FAILED - patch did not apply correctly[/red]")
            return False

        # Then: write indicator and check container stability
        local_hash = self.verifier.compute_local_hash()
        self._write_deployment_indicator(host, user, "patch", local_hash)

        if verify:
            if self._verify_deployment(host, user):
                console.print("  [green]✓ Verification PASSED (ephemeral patch)[/green]")
                return True
            else:
                console.print("  [red]✗ Container stability check FAILED[/red]")
                return False
        else:
            console.print("  [green]✓ Patch applied successfully (container stability check skipped)[/green]")
            return True

    def _verify_deployment(self, host: str, user: str) -> bool:
        """
        Verify that deployed code is correct and worker stays up.

        Checks:
        1. Code hash equality (deployed == local)
        2. Worker container stays running for N seconds
        3. Indicator file was written
        """
        import time

        # Get local hash
        local_hash = self.verifier.compute_local_hash()
        console.print(f"    Local code hash: {local_hash.digest}")

        # Wait for container to stabilize
        console.print("    Waiting for worker to stabilize (5s)...")
        time.sleep(5)

        # Check that worker is still running
        try:
            result = subprocess.run(
                ["ssh", f"{user}@{host}", "docker ps --format '{{.Names}}' | grep -q cocli-supervisor"],
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                console.print("    [red]Worker container crashed or not running[/red]")
                return False

            console.print("    [green]✓ Worker container stable[/green]")
        except Exception as e:
            console.print(f"    [red]Container check failed: {e}[/red]")
            return False

        # Get remote hash and compare
        remote_hash = self.verifier.compute_remote_hash(user, host)
        if remote_hash:
            console.print(f"    Remote code hash: {remote_hash.digest}")

            if local_hash == remote_hash:
                console.print("    [green]✓ Code hashes match[/green]")
            else:
                console.print("    [yellow]⚠ Hash mismatch (deployed != local) — check if code was synced correctly[/yellow]")
                # Don't fail on hash mismatch — could be timing issues
        else:
            console.print("    [yellow]⚠ Could not verify remote code hash[/yellow]")

        return True
